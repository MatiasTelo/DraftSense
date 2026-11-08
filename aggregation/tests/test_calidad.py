"""El módulo de validación y el Informe de Calidad de Datos — CA-410 a CA-415 y
`docs/27-validacion-confiabilidad.md`.

Los de la primera mitad no necesitan base: el alfa, la orientación, la concentración, el piso de los
segmentos y el bootstrap por respondedor son funciones puras. Los de la segunda arman su mundo con
`world`, como `test_pipeline.py`.
"""

from __future__ import annotations

import dataclasses
import uuid
from pathlib import Path

import numpy as np
import pytest
import sqlalchemy as sa

from aggregation import fits, pipeline, writers
from aggregation.load import Dataset, Row
from aggregation.quality import agreement, metrics, segments
from aggregation.quality.data import Extra, load_extra
from aggregation.quality.krippendorff import alpha
from app.models import Export, QuestionType
from tests.conftest import World, pairwise, requires_db, winner
from tests.test_estimadores import duel, params, row
from tests.test_pipeline import params as run_params
from tests.test_pipeline import populate

# ------------------------------------------------------------------------- alfa, CA-410


def test_ca410_el_alfa_es_el_del_ejemplo_de_krippendorff() -> None:
    """Krippendorff (2011), *Computing Krippendorff's Alpha-Reliability*: 4 observadores, 12
    unidades, valores 1 a 5 con faltantes. La unidad 12 tiene un solo valor y no aporta."""
    observers = [
        [1, 2, 3, 3, 2, 1, 4, 1, 2, None, None, None],
        [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, None, 3],
        [None, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, None],
        [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, None],
    ]
    units = [[v for v in column if v is not None] for column in zip(*observers, strict=True)]
    scale = [1, 2, 3, 4, 5]

    nominal = alpha(units, "nominal", scale)
    assert nominal.value == pytest.approx(0.743, abs=5e-4)
    assert (nominal.units, nominal.pairable) == (11, 40)
    assert alpha(units, "ordinal", scale).value == pytest.approx(0.815, abs=5e-4)
    assert alpha(units, "interval", scale).value == pytest.approx(0.849, abs=5e-4)


def test_ca410_sin_dos_valores_por_unidad_no_se_calcula() -> None:
    assert alpha([[1], [2], [3]], "nominal").value is None
    # Todos iguales: no hay desacuerdo esperado y el cociente no existe.
    assert alpha([[1, 1], [1, 1]], "nominal").value is None


def test_ca410_las_preguntas_armadas_al_reves_cuentan_como_acuerdo() -> None:
    """27 §2.3: la misma opinión sobre `(1, 2)` y sobre `(2, 1)` es acuerdo, no desacuerdo."""

    def lane(a: int, b: int, choice: str) -> Row:
        return row(
            QuestionType.LANE_MATCHUP, {"choice": choice}, champion_a=a, champion_b=b, role="mid"
        )

    rows = [
        lane(1, 2, "a_strong"),
        lane(2, 1, "b_strong"),  # la misma opinión: gana 1 por mucho
        lane(3, 4, "even"),
        lane(4, 3, "even"),
    ]
    data = Dataset(rows, {}, [1, 2, 3, 4], [], [], 1, "90.20")
    [mid] = [a for a in agreement.compute(data) if a.magnitude == "lane_strength · mid"]
    assert mid.result.value == pytest.approx(1.0)


def test_en_el_tipo_1_el_valor_es_el_lado() -> None:
    """27 §2.3: el valor es «ganó el de menor id» o «el de mayor», no el campeón.

    Un par dividido (1 contra 2) y uno unánime (gana 3). Por lado, los marginales son tres «menor»
    y un «mayor», y alfa da exactamente 0. Con el id como categoría habría tres categorías, el
    desacuerdo esperado subiría, y alfa daría 0.4 sin que la gente hubiera acordado más.
    """
    rows = [duel(1, 2), duel(2, 1), duel(3, 4), duel(3, 4)]
    data = Dataset(rows, {}, [1, 2, 3, 4], [(1, "engage")], [], 1, "90.20")
    [engage] = [a for a in agreement.compute(data) if a.magnitude == "score · engage"]
    assert engage.result.units == 2
    assert engage.result.value == pytest.approx(0.0)
    assert alpha([[1, 2], [3, 3]], "nominal").value == pytest.approx(0.4)


# ---------------------------------------------------------------- concentración, CA-413


def _from(person: uuid.UUID, r: Row) -> Row:
    return dataclasses.replace(r, respondent_id=person)


def test_ca413_un_decil_que_aporta_la_mitad_es_hallazgo() -> None:
    heavy = uuid.uuid4()
    rows = [_from(heavy, duel(1, 2)) for _ in range(50)]
    for _ in range(9):
        person = uuid.uuid4()
        rows += [_from(person, duel(2, 1)) for _ in range(50 // 9 + 1)][:6]
    index = metrics.concentration(rows)
    assert index.top == 1
    assert index.index is not None
    assert index.index > metrics.CONCENTRATION_LIMIT


def test_ca413_el_bootstrap_por_respondedor_es_mas_ancho() -> None:
    """Un respondedor que aporta casi todo y contra la mayoría: remuestrear personas lo hace
    aparecer o no, y el intervalo honesto es más ancho que el de comparaciones."""
    heavy = uuid.uuid4()
    rows = []
    for _ in range(20):
        rows += [_from(heavy, duel(1, 2)), _from(heavy, duel(2, 3)), _from(heavy, duel(1, 3))]
    for _ in range(9):
        person = uuid.uuid4()
        rows += [_from(person, duel(2, 1)), _from(person, duel(3, 2)), _from(person, duel(3, 1))]
    pool = [1, 2, 3]
    by_comparison = fits.fit_dimension("engage", rows, pool, params(200), np.random.default_rng(3))
    by_person = fits.fit_dimension_by_respondent(
        "engage", rows, pool, params(200), np.random.default_rng(3)
    )
    narrow = metrics.Magnitude("", "", [by_comparison.estimates[c] for c in pool]).mean_width()
    honest = metrics.Magnitude("", "", [by_person.estimates[c] for c in pool]).mean_width()
    assert narrow is not None and honest is not None
    assert honest > narrow
    # Los valores son los mismos: sólo cambia el intervalo.
    for c in pool:
        assert by_person.estimates[c].value == by_comparison.estimates[c].value


# ---------------------------------------------------------------------- segmentos, CA-414


def test_ca414_un_segmento_bajo_el_piso_no_se_calcula() -> None:
    def comparisons(people: int, each: int) -> list[Row]:
        out = []
        for _ in range(people):
            person = uuid.uuid4()
            out += [_from(person, duel(1, 2)) for _ in range(each)]
        return out

    small = segments.size(comparisons(14, 30), 15, 300)
    assert (small.respondents, small.comparisons, small.calculable) == (14, 420, False)
    enough = segments.size(comparisons(15, 20), 15, 300)
    assert enough.calculable


def test_los_segmentos_de_rango_son_los_de_25_3_5() -> None:
    from aggregation.quality.data import Person

    def person(rank: str | None) -> Person:
        return Person(uuid.uuid4(), rank, None, None, 0.5, False)

    assert segments.segment_of("rank", person("emerald")) == "mid"
    assert segments.segment_of("rank", person("challenger")) == "high"
    assert segments.segment_of("rank", person(None)) == "undeclared"
    assert segments.segment_of("rank", None) == "undeclared"
    assert segments.names("hours") == ["<5", "5-15", "15-30", "30+", "undeclared"]


# ------------------------------------------------------- test-retest y honeypots, con base


@requires_db
async def test_ca411_y_ca412_retests_y_honeypots(world: World) -> None:
    """Cuarenta personas contestan una honeypot: la mitad la falla y es consistente en el
    retest, la otra mitad la aprueba y no lo es. La honeypot es la sospechosa (27 §4.3). Una
    persona más, bajo `min_trust`, cuenta en el *pass rate* aunque no entre a la corrida."""
    honeypot = await world.question(
        **pairwise(world, 0, 1), is_honeypot=True, expected_answer={"choice": "a"}
    )
    peak = await world.question(
        type=QuestionType.PEAK_TIMING, champion_a=world.champions[2].champion_id
    )
    passing = winner(world, honeypot, 0)
    failing = winner(world, honeypot, 1)
    assert passing == {"choice": "a"}
    for i in range(40):
        person = await world.respondent()
        fails = i % 2 == 0
        await world.answer(person, honeypot, failing if fails else passing)
        original = await world.answer(person, peak, {"minute": 20})
        await world.answer(
            person, peak, {"minute": 21 if fails else 35}, is_retest_of=original.response_id
        )
    low = await world.respondent(trust="0.100")
    await world.answer(low, honeypot, passing)
    # Un retest del tipo 1 contestado `unknown` no forma par (22 §4).
    other = await world.respondent()
    duel_question = await world.question(**pairwise(world, 2, 3))
    first = await world.answer(other, duel_question, winner(world, duel_question, 2))
    await world.answer(other, duel_question, {"choice": "unknown"}, is_retest_of=first.response_id)

    extra = await load_extra(world.session, run_params())

    retests = {r.label: r for r in metrics.retest(extra)}
    assert (retests["Tipo 2 — pico"].pairs, retests["Tipo 2 — pico"].consistent) == (40, 20)
    assert retests["Tipo 1 — ranking"].pairs == 0
    [row_] = metrics.honeypots(extra, {c.champion_id: _info(c) for c in world.champions})
    assert (row_.attempts, row_.passed) == (41, 21)
    assert row_.failers == (20, 20)
    assert row_.passers == (0, 20)
    assert row_.suspicious
    assert extra.active_honeypots == [("90.20", 1)]


def _info(champion: object) -> object:
    from aggregation.load import ChampionInfo

    return ChampionInfo(
        champion_id=champion.champion_id,  # type: ignore[attr-defined]
        riot_key=champion.riot_key,  # type: ignore[attr-defined]
        display_name=champion.display_name,  # type: ignore[attr-defined]
        roles=(),
        pool_tier=1,
    )


# --------------------------------------------------------------------- el informe, CA-415


@requires_db
async def test_ca415_el_informe_no_toca_los_csv_y_queda_registrado(
    world: World, tmp_path: Path
) -> None:
    await populate(world)
    without = await pipeline.run(
        world.session, run_params(), tmp_path / "sin", workers=1, quality=False
    )
    full = await pipeline.run(world.session, run_params(), tmp_path / "con", workers=1)

    assert [f.sha256 for f in without.files] == [
        f.sha256 for f in full.files if f.kind in writers.KINDS
    ]
    [report] = [f for f in full.files if f.kind == "quality_report"]
    text = report.path.read_text(encoding="utf-8")
    assert text.startswith("# Informe de Calidad de Datos — v90.20")
    for heading in ("## Hallazgos", "## Acuerdo inter-anotador", "## Advertencias de lectura"):
        assert heading in text
    # Los SHA-256 de los seis CSV van en el encabezado.
    for csv in without.files:
        assert csv.sha256 in text

    [row_] = (
        await world.session.execute(
            sa.select(Export).where(
                Export.export_id.in_(full.export_ids), Export.file_kind == "quality_report"
            )
        )
    ).scalars()
    assert row_.file_name == "data_quality_report_v90.20.md"
    assert row_.sha256 == report.sha256
    assert row_.row_count == text.count("\n")
    assert row_.column_count == 0
    assert row_.responses_included == full.responses


def test_extra_y_dataset_son_lo_que_el_informe_espera() -> None:
    """Un recordatorio para quien agregue un campo: el informe no lee nada que no esté acá."""
    assert {f.name for f in dataclasses.fields(Extra)} >= {
        "people",
        "honeypots",
        "honeypot_answers",
        "retests",
        "active_honeypots",
        "excluded",
        "settings",
    }
