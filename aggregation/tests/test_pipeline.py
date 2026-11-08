"""La corrida completa contra la base: CA-407, CA-408, CA-409 y `docs/25-agregacion.md` §1.3,
§3.2 y §7. Arman su propio mundo con `world` y lo revierte la transacción del test."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa

from aggregation import pipeline, writers
from aggregation.load import NoDataError, load
from aggregation.params import DEFAULT_SUPPORT_THRESHOLDS, RunParams
from app.models import Export, LaneRole, QuestionType
from tests.conftest import World, pairwise, requires_db, winner

pytestmark = requires_db

EXPORTED_AT = dt.date(2030, 3, 15)


def params(window: tuple[str, str] = ("90.20", "90.20"), bootstrap: int = 40) -> RunParams:
    return RunParams(
        patch_from=window[0],
        patch_to=window[1],
        min_trust=Decimal("0.300"),
        halflife=21.0,
        sigma=7.5,
        bootstrap=bootstrap,
        exported_at=EXPORTED_AT,
        bt_prior=0.5,
        lambda_champion=0.10,
        lambda_interaction=1.00,
        max_iter=500,
        tol=1e-9,
        support_thresholds=DEFAULT_SUPPORT_THRESHOLDS,
    )


async def populate(world: World) -> None:
    """Un poco de cada tipo: lo justo para que los seis archivos tengan filas."""
    people = [await world.respondent() for _ in range(4)]
    mid = [0, 1, 2]
    for person in people:
        for a, b in [(0, 1), (1, 2), (0, 2)]:
            question = await world.question(**pairwise(world, a, b))
            await world.answer(person, question, winner(world, question, a))
        peak = await world.question(
            type=QuestionType.PEAK_TIMING, champion_a=world.champions[0].champion_id
        )
        await world.answer(person, peak, {"minute": 20})
        traits = await world.question(
            type=QuestionType.TRAIT_MULTISELECT, champion_a=world.champions[1].champion_id
        )
        await world.answer(person, traits, {"traits": ["aggalpha"]})
        low, high = sorted(world.champions[i].champion_id for i in mid[:2])
        lane = await world.question(
            type=QuestionType.LANE_MATCHUP, champion_a=low, champion_b=high, role=LaneRole.MID
        )
        await world.answer(person, lane, {"choice": "a_slight"})


async def hashes(world: World, tmp_path: Path, name: str, **kwargs: object) -> list[str]:
    """Los SHA-256 de los seis CSV. El informe describe también lo que la corrida deja afuera
    —honeypots, retests, rango declarado—, así que cambia donde los CSV no deben cambiar."""
    result = await pipeline.run(world.session, params(**kwargs), tmp_path / name, workers=1)  # type: ignore[arg-type]
    return [f.sha256 for f in result.files if f.kind in writers.KINDS]


async def test_ca408_la_misma_corrida_da_el_mismo_hash(world: World, tmp_path: Path) -> None:
    """CA-408 y CA-415: los siete archivos, el informe incluido."""
    await populate(world)
    first = await pipeline.run(world.session, params(), tmp_path / "uno", workers=1)
    second = await pipeline.run(world.session, params(), tmp_path / "dos", workers=1)
    assert len(first.files) == len(writers.KINDS) + 1
    assert [f.sha256 for f in first.files] == [f.sha256 for f in second.files]


async def test_en_paralelo_o_en_serie_da_lo_mismo(world: World, tmp_path: Path) -> None:
    """La partición de trabajo es parte del contrato (§8.2, nota del 29/10)."""
    await populate(world)
    serial = await pipeline.run(world.session, params(), tmp_path / "serie", workers=1)
    parallel = await pipeline.run(world.session, params(), tmp_path / "paralelo", workers=3)
    assert [f.sha256 for f in serial.files] == [f.sha256 for f in parallel.files]


async def test_ca407_una_fila_de_exports_por_archivo(world: World, tmp_path: Path) -> None:
    await populate(world)
    result = await pipeline.run(world.session, params(), tmp_path / "x", workers=1)
    rows = list(
        (
            await world.session.execute(
                sa.select(Export).where(Export.export_id.in_(result.export_ids))
            )
        ).scalars()
    )
    assert sorted(r.file_kind for r in rows) == sorted([*writers.KINDS, "quality_report"])
    for row in rows:
        assert row.patch_window == "90.20..90.20"
        assert row.min_trust_applied == Decimal("0.300")
        assert row.params["power_sigma"] == 7.5
        assert row.params["exported_at"] == "2030-03-15"
        assert row.params["support_thresholds"] == DEFAULT_SUPPORT_THRESHOLDS
        assert len(row.sha256) == 64
    names = {p.name for p in (tmp_path / "x").iterdir()}
    assert names == {f"{kind}_v90.20.csv" for kind in writers.KINDS} | {
        "data_quality_report_v90.20.md"
    }


async def test_el_rango_declarado_no_pondera(world: World, tmp_path: Path) -> None:
    """§3.2: cambiar `declared_rank` no cambia ni un byte."""
    await populate(world)
    before = await hashes(world, tmp_path, "antes")
    for person in world.respondents:
        person.declared_rank = "challenger"
    await world.session.commit()
    assert await hashes(world, tmp_path, "despues") == before


async def test_honeypots_y_retests_no_entran(world: World, tmp_path: Path) -> None:
    """§1.3: agregar una honeypot respondida y un retest no cambia ninguna celda."""
    await populate(world)
    before = await hashes(world, tmp_path, "antes")
    person = world.respondents[0]
    honeypot = await world.question(
        **pairwise(world, 3, 4), is_honeypot=True, expected_answer={"choice": "a"}
    )
    await world.answer(person, honeypot, {"choice": "b"})
    original = (
        await world.session.execute(
            sa.text(
                "SELECT response_id, question_id FROM responses "
                "WHERE respondent_id = :r AND type = 'peak_timing'"
            ),
            {"r": person.respondent_id},
        )
    ).first()
    assert original is not None
    peak = next(q for q in world.questions.values() if q.question_id == original.question_id)
    await world.answer(person, peak, {"minute": 39}, is_retest_of=original.response_id)
    assert await hashes(world, tmp_path, "despues") == before


async def test_ca409_la_ventana_excluye_y_el_decaimiento_pesa(world: World) -> None:
    """16.19..16.20 deja afuera a 16.18, y lo más viejo pesa menos."""
    person = await world.respondent()
    for name, created in (
        ("old", dt.datetime(2030, 1, 10, tzinfo=dt.UTC)),
        ("mid", dt.datetime(2030, 2, 10, tzinfo=dt.UTC)),
        ("current", dt.datetime(2030, 3, 10, tzinfo=dt.UTC)),
    ):
        question = await world.question(
            type=QuestionType.PEAK_TIMING,
            champion_a=world.champions[0].champion_id,
            patch_id=world.patches[name].patch_id,
        )
        await world.answer(person, question, {"minute": 20}, created=created)
    data = await load(world.session, params(window=("90.19", "90.20")))
    patches = {r.patch_id for r in data.rows}
    assert world.patches["old"].patch_id not in patches
    weights = {r.patch_id: r.weight for r in data.rows}
    assert weights[world.patches["mid"].patch_id] < weights[world.patches["current"].patch_id]


async def test_sin_respuestas_falla_y_no_escribe(world: World, tmp_path: Path) -> None:
    """§7: un CSV vacío con su hash registrado sería peor que no tener corrida."""
    with pytest.raises(NoDataError):
        await pipeline.run(world.session, params(), tmp_path / "nada", workers=1)
    assert not (tmp_path / "nada").exists()


async def test_el_trust_bajo_el_umbral_queda_afuera(world: World) -> None:
    """26 §2.6: el umbral filtra sin borrar."""
    low = await world.respondent(trust="0.200")
    question = await world.question(
        type=QuestionType.PEAK_TIMING, champion_a=world.champions[0].champion_id
    )
    await world.answer(low, question, {"minute": 10})
    with pytest.raises(NoDataError):
        await load(world.session, params())
