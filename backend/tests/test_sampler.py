"""El sampler completo — `docs/21-sampler.md` §11 y CA-101/CA-102.

Lo que cubre `test_questions.py` (el render, la materialización, el arranque) no se repite acá.
Estos tests miran lo que agregó la semana 5: la prioridad, los dos regímenes, la regla de
variedad, los puentes y la cadencia.

**Sobre la mezcla de ±5 puntos de §11:** se mide con los seis tipos, en la semana 8. Con los tres de
hoy, la regla de variedad corta las rachas del tipo 1 y su proporción real baja del 59 %
renormalizado a alrededor del 53 %. `test_questions.py` verifica la mezcla sin la regla, y acá se
verifica la regla.
"""

from __future__ import annotations

import datetime as dt
import logging
import random
import uuid
from collections import Counter
from decimal import Decimal
from itertools import groupby

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Champion,
    Dimension,
    LaneRole,
    Patch,
    Question,
    QuestionType,
    Respondent,
    Response,
)
from app.services import responses as responses_service
from app.services import sampler, sessions
from app.services.questions import Space, draw_combination
from app.services.sampler import (
    DEFAULT_WEIGHTS,
    SamplerConfig,
    choose_type,
    open_windows,
)
from tests.conftest import (
    FAR,
    add_response,
    as_respondent,
    make_champions,
    make_dimensions,
    pairwise_question,
    requires_db,
    restrict_pool,
    set_setting,
)

PAIRWISE = QuestionType.PAIRWISE_DIMENSION
PEAK = QuestionType.PEAK_TIMING
LANE = QuestionType.LANE_MATCHUP
SERVED = frozenset({PAIRWISE, PEAK, LANE})


def _champion(champion_id: int, roles: list[LaneRole]) -> Champion:
    return Champion(
        champion_id=champion_id,
        riot_key=f"K{champion_id}",
        riot_name=f"C{champion_id}",
        display_name=f"C{champion_id}",
        roles=roles,
        image_url="https://example.invalid/x.png",
        patch_first_seen=1,
        pool_tier=1,
    )


def _dimension(dimension_id: int) -> Dimension:
    return Dimension(
        dimension_id=dimension_id,
        code=f"d{dimension_id}",
        label_en="D",
        description_en="",
        prompt_en="",
    )


# ------------------------------------------------------------------------------ sin base de datos


def test_nunca_cuatro_seguidas_del_mismo_tipo() -> None:
    """La regla de variedad de §6, sobre una sesión larga simulada."""
    rng = random.Random(42)
    sequence: list[QuestionType] = []
    for position in range(5_000):
        chosen = choose_type(position, SERVED, rng, sequence)
        assert chosen is not None
        sequence.append(chosen)
    runs = [len(list(group)) for _, group in groupby(sequence)]
    assert max(runs) <= 3


def test_tras_tres_iguales_ese_tipo_sale_del_sorteo() -> None:
    rng = random.Random(7)
    draws = {choose_type(10, SERVED, rng, [PAIRWISE] * 3) for _ in range(2_000)}
    assert PAIRWISE not in draws
    assert draws == {PEAK, LANE}


def test_si_no_hay_otro_tipo_se_permite_la_cuarta() -> None:
    """Un lote corto es peor que una cuarta seguida."""
    assert choose_type(10, {PEAK}, random.Random(1), [PEAK] * 3) is PEAK


def test_el_arranque_esta_por_encima_de_la_variedad() -> None:
    """§6 — la regla de arriba gana: las tres primeras son de tipo 1 igual."""
    rng = random.Random(3)
    assert choose_type(2, SERVED, rng, [PAIRWISE] * 3) is PAIRWISE


def test_el_rol_del_1v1_se_pesa_por_su_cantidad_de_pares() -> None:
    """Errata de §4.4 — uniforme sobre (par, rol): 1 par en top contra 6 en mid da 1/7 para top."""
    champions = [_champion(i, [LaneRole.TOP]) for i in (1, 2)] + [
        _champion(i, [LaneRole.MID]) for i in (3, 4, 5, 6)
    ]
    space = Space.of(champions, [])
    rng = random.Random(11)
    roles = Counter(draw_combination(LANE, space, rng).role for _ in range(20_000))
    assert roles[LaneRole.TOP] / 20_000 == pytest.approx(1 / 7, abs=0.02)


def test_la_exploracion_es_uniforme_sobre_los_campeones() -> None:
    """§11 — con ε = 1, la distribución de campeones es uniforme dentro del error de muestreo."""
    space = Space.of([_champion(i, [LaneRole.MID]) for i in range(1, 11)], [_dimension(1)])
    rng = random.Random(5)
    appearances: Counter[int] = Counter()
    draws = 20_000
    for _ in range(draws):
        combination = draw_combination(PAIRWISE, space, rng)
        assert combination.champion_b is not None
        appearances.update((combination.champion_a, combination.champion_b))
    for champion_id in range(1, 11):
        assert appearances[champion_id] / draws == pytest.approx(0.2, abs=0.02)


def test_los_pesos_por_defecto_son_los_del_documento() -> None:
    """§3 — el puente pesa 1.00 y los otros tres suman 0.80: cualquier puente gana."""
    assert DEFAULT_WEIGHTS == {
        "escasez": 0.35,
        "informacion": 0.25,
        "cobertura": 0.20,
        "puente": 1.0,
    }
    others = sum(v for k, v in DEFAULT_WEIGHTS.items() if k != "puente")
    assert others < DEFAULT_WEIGHTS["puente"]


def _config() -> SamplerConfig:
    return SamplerConfig(
        epsilon=1.0,
        weights=DEFAULT_WEIGHTS,
        cold_threshold=5,
        candidate_limit=50,
        max_retries=10,
        honeypot_every=(10, 15),
        retest_every=30,
        retest_min_distance=15,
    )


def test_las_ventanas_se_abren_desde_donde_esta_el_respondedor() -> None:
    """ADR-020 — honeypot entre las posiciones 9 y 14, retest en la 29, contando desde hoy."""
    for answers_count in (0, 50):
        respondent = Respondent(answers_count=answers_count)
        open_windows(respondent, _config(), random.Random(answers_count))
        assert respondent.next_honeypot_at is not None
        assert answers_count + 9 <= respondent.next_honeypot_at <= answers_count + 14
        assert respondent.next_retest_at == answers_count + 29


def test_una_ventana_abierta_no_se_vuelve_a_sortear() -> None:
    respondent = Respondent(answers_count=3, next_honeypot_at=7, next_retest_at=40)
    open_windows(respondent, _config(), random.Random(0))
    assert (respondent.next_honeypot_at, respondent.next_retest_at) == (7, 40)


# ------------------------------------------------------------------------------- con base de datos


async def _ready(
    db: AsyncSession,
    respondent: Respondent,
    champions: list[Champion],
    dimensions: list[Dimension],
    epsilon: float,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pool reducido, ε fijo, sólo tipo 1, sin arranque ni cadencias."""
    await restrict_pool(db, champions, dimensions)
    await set_setting(db, "sampler.epsilon", epsilon)
    monkeypatch.setattr(sampler, "TYPE_WEIGHTS", {PAIRWISE: 1})
    respondent.answers_count = 3
    respondent.next_honeypot_at = FAR
    respondent.next_retest_at = FAR
    await db.commit()


async def _ids(client: AsyncClient, token: str, count: int) -> list[int]:
    response = await as_respondent(client, token).get(f"/questions/next?count={count}")
    assert response.status_code == 200
    return [q["question_id"] for q in response.json()["questions"]]


@requires_db
async def test_el_puente_domina(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§11 — un puente muy expuesto le gana a la mejor pregunta sin puente."""
    row, token = respondent
    await _ready(db, row, champions, [dimension], 0.0, monkeypatch)
    bridge = await pairwise_question(
        db,
        patch,
        champions[0],
        champions[1],
        dimension,
        bridge_priority=True,
        exposure_count=500,
        entropy=Decimal("0"),
    )
    best = await pairwise_question(
        db,
        patch,
        champions[2],
        champions[3],
        dimension,
        exposure_count=5,
        entropy=Decimal("1"),
        coverage_deficit=Decimal("1"),
    )

    assert await _ids(client, token, 2) == [bridge.question_id, best.question_id]


@requires_db
async def test_la_explotacion_ordena_por_prioridad(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§3 — con ε = 0, la más disputada primero; la escasez y la cobertura suman."""
    row, token = respondent
    await _ready(db, row, champions, [dimension], 0.0, monkeypatch)
    settled = await pairwise_question(
        db, patch, champions[0], champions[1], dimension, exposure_count=40, entropy=Decimal("0.1")
    )
    disputed = await pairwise_question(
        db, patch, champions[0], champions[2], dimension, exposure_count=40, entropy=Decimal("0.9")
    )
    scarce = await pairwise_question(
        db, patch, champions[0], champions[3], dimension, exposure_count=5, entropy=Decimal("0.1")
    )

    assert await _ids(client, token, 3) == [
        disputed.question_id,
        scarce.question_id,
        settled.question_id,
    ]


@requires_db
async def test_el_estrato_frio_no_compite_por_prioridad(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-012 — con menos de 5 respuestas una pregunta no entra a la explotación."""
    row, token = respondent
    await _ready(db, row, champions, [dimension], 0.0, monkeypatch)
    hot = await pairwise_question(
        db, patch, champions[0], champions[1], dimension, exposure_count=5, entropy=Decimal("0")
    )
    await pairwise_question(
        db, patch, champions[2], champions[3], dimension, exposure_count=4, entropy=Decimal("1")
    )

    assert (await _ids(client, token, 1)) == [hot.question_id]


@requires_db
async def test_sin_estrato_caliente_se_cae_a_la_exploracion(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nota del 16/09 en §5 — con ε = 0 y nada caliente, el lote no sale vacío."""
    row, token = respondent
    await _ready(db, row, champions, [dimension], 0.0, monkeypatch)

    served = await _ids(client, token, 3)

    assert len(served) == 3
    assert len(set(served)) == 3


@requires_db
async def test_la_exploracion_nunca_sirve_una_honeypot(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nota del 16/09 en §5 — de tres pares, dos son honeypot: sólo sale el tercero."""
    row, token = respondent
    trio = champions[:3]
    await _ready(db, row, trio, [dimension], 1.0, monkeypatch)
    # Con 10 reintentos, dos de cada tres sorteos caen en una honeypot y el lote podría salir
    # vacío por mala suerte (un 2 % de las veces). Con 60, la probabilidad es despreciable.
    await set_setting(db, "sampler.max_rejection_retries", 60)
    traps = {
        (
            await pairwise_question(
                db, patch, a, b, dimension, is_honeypot=True, expected_answer={"choice": "a"}
            )
        ).question_id
        for a, b in [(trio[0], trio[1]), (trio[0], trio[2])]
    }

    for _ in range(5):
        served = await _ids(client, token, 1)
        assert served and served[0] not in traps


@requires_db
async def test_la_variedad_mira_las_respuestas_anteriores(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """Tres respuestas de tipo 1 ya dadas: la cuarta posición no puede ser de tipo 1."""
    row, token = respondent
    await restrict_pool(db, champions, [dimension])
    for a, b in [(0, 1), (0, 2), (0, 3)]:
        question = await pairwise_question(db, patch, champions[a], champions[b], dimension)
        await add_response(db, row, question, {"choice": "a"})
    row.next_honeypot_at = FAR
    row.next_retest_at = FAR
    await db.commit()

    response = await as_respondent(client, token).get("/questions/next?count=1")

    assert response.json()["questions"][0]["type"] != "pairwise_dimension"


@requires_db
async def test_un_rol_salteado_queda_en_el_log(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """§8 — un rol sin pareja no es un error, pero se registra."""
    await restrict_pool(db, champions, [dimension])
    _, token = respondent

    with caplog.at_level(logging.INFO, logger="app.services.sampler"):
        await _ids(client, token, 1)

    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "top" in messages and "adc" in messages
    assert "mid" not in messages.split(":")[-1]


@requires_db
async def test_doscientas_preguntas_sin_repetir_ni_precomputar(
    db: AsyncSession, patch: Patch
) -> None:
    """§11 — nadie repite pregunta salvo los retests, y la tabla crece con lo servido.

    Corre sobre el service y no por HTTP para no pagar 400 viajes; el `POST` se emula con
    `responses.record`, que es lo que llama el router y lo que reconoce los retests.
    """
    champions = await make_champions(db, patch, 16, prefix="Big")
    dimensions = await make_dimensions(db, ["bigdima", "bigdimb", "bigdimc"])
    await restrict_pool(db, champions, dimensions)
    await set_setting(db, "sampler.epsilon", 1.0)
    respondent, _ = await sessions.create(db, f"huella-sampler-{uuid.uuid4()}")
    rng = random.Random(2026)
    now = dt.datetime.now(dt.UTC)

    served: list[int] = []
    while len(served) < 200:
        batch = await sampler.next_batch(db, respondent, 10, rng)
        assert batch
        for item in batch[: 200 - len(served)]:
            question = await db.get(Question, item.question_id)
            assert question is not None
            answer = (
                {"minute": 20}
                if question.type is PEAK
                else {"choice": "even" if question.type is LANE else "a"}
            )
            await responses_service.record(db, respondent, question, answer, 2500, now, rng)
            served.append(item.question_id)

    rows = list(
        (
            await db.execute(
                sa.select(Response.question_id, Response.is_retest_of).where(
                    Response.respondent_id == respondent.respondent_id
                )
            )
        ).tuples()
    )
    originals = [question_id for question_id, retest_of in rows if retest_of is None]
    retests = [question_id for question_id, retest_of in rows if retest_of is not None]
    assert len(originals) == len(set(originals))
    assert set(retests) <= set(originals)
    assert len(retests) >= 5  # posiciones 29, 59, …, 179

    stored = (
        await db.execute(
            sa.select(sa.func.count())
            .select_from(Question)
            .where(Question.patch_id == patch.patch_id)
        )
    ).scalar_one()
    assert stored == len(set(originals))


@requires_db
async def test_las_dos_ramas_respetan_el_pool_de_ahora(
    db: AsyncSession, patch: Patch, dimension: Dimension
) -> None:
    """Una pregunta caliente con un campeón que bajó de tier no se vuelve a servir (§8)."""
    champions = await make_champions(db, patch, 4, prefix="Tier")
    await restrict_pool(db, champions, [dimension])
    await set_setting(db, "sampler.epsilon", 0.0)
    stale = await pairwise_question(
        db, patch, champions[0], champions[1], dimension, exposure_count=9, entropy=Decimal("1")
    )
    champions[0].pool_tier = 3
    await db.commit()
    respondent, _ = await sessions.create(db, f"huella-tier-{uuid.uuid4()}")
    respondent.answers_count = 3
    respondent.next_honeypot_at = FAR
    respondent.next_retest_at = FAR
    await db.commit()

    for _ in range(3):
        batch = await sampler.next_batch(db, respondent, 5, random.Random(1))
        assert stale.question_id not in {q.question_id for q in batch}


@requires_db
async def test_queued_invalido(client: AsyncClient, respondent: tuple[Respondent, str]) -> None:
    """`docs/12-api.md` §2.3, nota del 17/09 — hasta 10 ids enteros y positivos."""
    _, token = respondent
    for value in ("abc", "1,,2", "0", "-3", ",".join(str(i) for i in range(1, 12))):
        response = await as_respondent(client, token).get(f"/questions/next?queued={value}")
        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "invalid_parameter"
        assert error["field"] == "queued"


@requires_db
async def test_lo_que_esta_en_cola_no_se_vuelve_a_servir(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-020 — el puente es determinista: sin `queued`, el lote siguiente lo repetía."""
    row, token = respondent
    await _ready(db, row, champions, [dimension], 1.0, monkeypatch)
    bridge = await pairwise_question(
        db, patch, champions[0], champions[1], dimension, bridge_priority=True
    )

    first = await _ids(client, token, 1)
    again = await _ids(client, token, 1)
    response = await as_respondent(client, token).get(
        f"/questions/next?count=1&queued={bridge.question_id}"
    )

    assert first == again == [bridge.question_id]
    assert response.json()["questions"][0]["question_id"] != bridge.question_id
