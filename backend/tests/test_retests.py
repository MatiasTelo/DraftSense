"""Test-retest — CA-204 y CA-205 de `03-criterios-aceptacion.md` §3, y `22-calidad-de-datos.md` §4.

Desde ADR-020 el retest lo marca el servidor: el sampler lo sirve, guarda la respuesta original en
`respondents.pending_retest_of`, y el `POST` de siempre se registra con `is_retest_of`.

El mecanismo común se prueba con el tipo 3. El tipo 1 tiene su propia sección al final: desde
ADR-022 su retest es el par de las puntas de un ranking (22 §4.1).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal
from itertools import combinations
from typing import Any

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
    Ranking,
    Respondent,
    Response,
)
from app.services import questions
from app.services import responses as responses_service
from app.services.questions import Combination
from app.services.retests import is_consistent
from tests.conftest import (
    FAR,
    add_response,
    as_respondent,
    make_champions,
    make_dimensions,
    requires_db,
    restrict_pool,
)

PAIRWISE = QuestionType.PAIRWISE_DIMENSION
PEAK = QuestionType.PEAK_TIMING
LANE = QuestionType.LANE_MATCHUP


# ------------------------------------------------------------------------------ sin base de datos


@pytest.mark.parametrize(
    ("question_type", "first", "second", "expected"),
    [
        (PAIRWISE, {"choice": "a"}, {"choice": "a"}, True),
        (PAIRWISE, {"choice": "a"}, {"choice": "b"}, False),
        (PAIRWISE, {"choice": "unknown"}, {"choice": "a"}, None),
        (PAIRWISE, {"choice": "b"}, {"choice": "unknown"}, None),
        (LANE, {"choice": "a_strong"}, {"choice": "a_slight"}, True),
        (LANE, {"choice": "even"}, {"choice": "even"}, True),
        (LANE, {"choice": "a_slight"}, {"choice": "even"}, False),
        (LANE, {"choice": "a_strong"}, {"choice": "b_strong"}, False),
        (PEAK, {"minute": 20}, {"minute": 25}, True),
        (PEAK, {"minute": 20}, {"minute": 15}, True),
        (PEAK, {"minute": 20}, {"minute": 26}, False),
        (QuestionType.DUO_SYNERGY, {"choice": "pair_1"}, {"choice": "pair_1"}, None),
    ],
)
def test_que_cuenta_como_consistente(
    question_type: QuestionType,
    first: dict[str, Any],
    second: dict[str, Any],
    expected: bool | None,
) -> None:
    """§4 — se mide consistencia, no memoria: *wins hard* y *wins slightly* son la misma opinión."""
    assert is_consistent(question_type, first, second) is expected


# ------------------------------------------------------------------------------- con base de datos


async def _history(
    db: AsyncSession,
    patch: Patch,
    respondent: Respondent,
    n: int,
    answer: Callable[[int], dict[str, Any]] = lambda _: {"choice": "a_slight"},
) -> tuple[list[Response], list[Champion], list[Dimension]]:
    """`n` respuestas de tipo 3 en posiciones 0 … n-1, sobre un pool propio y habilitado.

    Son de tipo 3 y no de tipo 1 porque desde ADR-022 el retest del tipo 1 sale de un ranking y
    tiene su propia sección. El mecanismo —cadencia, distancia, marca del servidor— es el mismo.
    """
    champions = await make_champions(db, patch, 8, prefix="Rt")
    dimensions = await make_dimensions(db, ["rtdima", "rtdimb"])
    await restrict_pool(db, champions, dimensions)
    pairs = [
        (a, b, role)
        for role in (LaneRole.TOP, LaneRole.MID)
        for a, b in combinations(champions, 2)
    ]
    rows = []
    for index, (a, b, role) in enumerate(pairs[:n]):
        low, high = sorted((a.champion_id, b.champion_id))
        question = await questions.materialize(
            db, patch.patch_id, Combination(LANE, low, champion_b=high, role=role)
        )
        rows.append(await add_response(db, respondent, question, answer(index)))
    return rows, champions, dimensions


async def _due(db: AsyncSession, respondent: Respondent) -> None:
    """El retest toca en la próxima posición; la honeypot, nunca."""
    respondent.next_retest_at = respondent.answers_count
    respondent.next_honeypot_at = FAR
    await db.commit()


async def _next_id(client: AsyncClient) -> int:
    response = await client.get("/questions/next?count=1")
    assert response.status_code == 200
    batch = response.json()["questions"]
    assert len(batch) == 1
    question_id: int = batch[0]["question_id"]
    return question_id


async def _rows_for(db: AsyncSession, respondent_id: uuid.UUID, question_id: int) -> list[Response]:
    return list(
        (
            await db.execute(
                sa.select(Response)
                .where(
                    Response.respondent_id == respondent_id,
                    Response.question_id == question_id,
                )
                .order_by(Response.response_id)
            )
        ).scalars()
    )


@requires_db
async def test_ca205_el_retest_se_registra_con_su_original(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    row, token = respondent
    history, _, _ = await _history(db, patch, row, 16)
    await _due(db, row)
    http = as_respondent(client, token)

    question_id = await _next_id(http)

    # Posición 16, distancia mínima 15: sólo califican las respuestas de las posiciones 0 y 1.
    by_question = {r.question_id: r for r in history[:2]}
    assert question_id in by_question
    await db.refresh(row)
    assert row.pending_retest_of == by_question[question_id].response_id

    posted = await http.post(
        "/responses",
        json={
            "question_id": question_id,
            "answer": {"choice": "a_strong"},
            "response_time_ms": 2100,
        },
    )
    assert posted.status_code == 201

    first, repeat = await _rows_for(db, row.respondent_id, question_id)
    assert repeat.is_retest_of == first.response_id
    await db.refresh(row)
    assert (row.retest_pairs, row.retest_consistent) == (1, 1)
    assert row.pending_retest_of is None
    assert row.next_retest_at == 16 + 30
    assert row.trust_score == Decimal("0.567")


@requires_db
async def test_ca204_el_doble_toque_sobre_un_retest_devuelve_409(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    """La marca se consume con el primer envío: el segundo es un duplicado común."""
    row, token = respondent
    respondent_id = row.respondent_id
    await _history(db, patch, row, 16)
    await _due(db, row)
    http = as_respondent(client, token)
    question_id = await _next_id(http)
    body = {"question_id": question_id, "answer": {"choice": "b_slight"}, "response_time_ms": 1900}

    assert (await http.post("/responses", json=body)).status_code == 201
    second = await http.post("/responses", json=body)

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_response"
    # El INSERT fallido dejó la sesión compartida en rollback; con `create_savepoint` esto sólo
    # descarta el savepoint del segundo envío, y el primero sigue en la transacción del test.
    await db.rollback()
    assert len(await _rows_for(db, respondent_id, question_id)) == 2


@requires_db
async def test_un_retest_inconsistente_baja_el_trust(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    row, token = respondent
    await _history(db, patch, row, 16)
    await _due(db, row)
    http = as_respondent(client, token)
    question_id = await _next_id(http)

    await http.post(
        "/responses",
        json={
            "question_id": question_id,
            "answer": {"choice": "b_slight"},
            "response_time_ms": 1900,
        },
    )

    await db.refresh(row)
    assert (row.retest_pairs, row.retest_consistent) == (1, 0)
    assert row.trust_score == Decimal("0.433")


@requires_db
async def test_sin_marca_la_repeticion_es_un_duplicado(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    """CA-204 — sin retest pendiente, repetir una pregunta vieja es 409, aunque esté lejos."""
    row, token = respondent
    history, _, _ = await _history(db, patch, row, 16)

    response = await as_respondent(client, token).post(
        "/responses",
        json={
            "question_id": history[0].question_id,
            "answer": {"choice": "a_slight"},
            "response_time_ms": 2000,
        },
    )

    assert response.status_code == 409


@requires_db
async def test_el_retest_pendiente_se_vuelve_a_servir(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    """Si el lote se pierde, el mismo retest vuelve: no se elige otro (ADR-020)."""
    row, token = respondent
    await _history(db, patch, row, 16)
    await _due(db, row)
    http = as_respondent(client, token)

    first = await _next_id(http)
    await db.refresh(row)
    pending = row.pending_retest_of
    second = await _next_id(http)

    assert first == second
    await db.refresh(row)
    assert row.pending_retest_of == pending


@requires_db
async def test_no_se_repite_una_honeypot_ni_algo_ya_retesteado(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    row, token = respondent
    history, _, _ = await _history(db, patch, row, 16)
    honeypot = history[0]
    await db.execute(
        sa.update(Question)
        .where(Question.question_id == honeypot.question_id)
        .values(is_honeypot=True, expected_answer={"choice": "a_slight"})
    )
    # Un retest ya dado sobre la posición 1 la saca de las elegibles y corre las posiciones.
    repeated = history[1]
    question = await db.get(Question, repeated.question_id)
    assert question is not None
    await add_response(
        db, row, question, {"choice": "a_slight"}, is_retest_of=repeated.response_id
    )
    await _due(db, row)

    question_id = await _next_id(as_respondent(client, token))

    # Posición 17: califican las posiciones 0, 1 y 2, menos la honeypot y la ya retesteada.
    assert question_id == history[2].question_id


@requires_db
async def test_agotado_todo_se_sirve_un_retest(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    """`21-sampler.md` §8 — el camino existe y está probado."""
    row, token = respondent
    champions = await make_champions(db, patch, 4, prefix="Ag")
    dimensions = await make_dimensions(db, ["agdima", "agdimb"])
    await restrict_pool(db, champions, dimensions)
    every: list[Combination] = []
    for a, b in combinations(sorted(c.champion_id for c in champions), 2):
        every += [
            Combination(PAIRWISE, a, champion_b=b, dimension_id=d.dimension_id) for d in dimensions
        ]
        every += [
            Combination(LANE, a, champion_b=b, role=role) for role in (LaneRole.TOP, LaneRole.MID)
        ]
    every += [Combination(PEAK, c.champion_id) for c in champions]
    answered = []
    for combination in every:
        question = await questions.materialize(db, patch.patch_id, combination)
        answer: dict[str, Any] = (
            {"minute": 20}
            if combination.type is PEAK
            else {"choice": "even" if combination.type is LANE else "a"}
        )
        answered.append(await add_response(db, row, question, answer))
    row.next_retest_at = FAR
    row.next_honeypot_at = FAR
    await db.commit()

    question_id = await _next_id(as_respondent(client, token))

    assert question_id in {r.question_id for r in answered}
    await db.refresh(row)
    assert row.pending_retest_of is not None


@requires_db
async def test_con_cola_el_retest_cae_en_su_posicion(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    """Catorce respuestas y dos en cola: la primera pregunta del lote ocupa la posición 16."""
    row, token = respondent
    history, _, _ = await _history(db, patch, row, 14)
    row.next_retest_at = 16
    row.next_honeypot_at = FAR
    await db.commit()
    http = as_respondent(client, token)

    without_queue = (await http.get("/questions/next?count=1")).json()["questions"]
    await db.refresh(row)
    assert row.pending_retest_of is None
    # Los ids en cola no tienen que existir: el servidor sólo los cuenta y no los repite.
    queued = "999999991,999999992"
    with_queue = (await http.get(f"/questions/next?count=1&queued={queued}")).json()["questions"]

    # Sin la cola, el servidor cree que la pregunta cae en la 14 y el retest todavía no toca.
    assert without_queue[0]["question_id"] not in {r.question_id for r in history}
    # Posición 16, distancia 15: califican las respuestas de las posiciones 0 y 1.
    assert with_queue[0]["question_id"] in {history[0].question_id, history[1].question_id}


# --------------------------------------------------------- tipo 1: el par de las puntas (ADR-022)


async def _rankings(
    db: AsyncSession,
    patch: Patch,
    respondent: Respondent,
    n: int,
    not_sure: Callable[[int], bool] = lambda _: False,
) -> list[Ranking]:
    """`n` rankings contestados en posiciones 0 … n-1, cada uno en una dimensión propia.

    Una dimensión por ranking para que ningún par se repita: así cada par de las puntas tiene su
    respuesta en el ranking que lo produjo. Se registran con el servicio real, que es el que
    escribe las diez filas y el `submitted_order`.
    """
    champions = await make_champions(db, patch, 8, prefix="Rk")
    dimensions = await make_dimensions(db, [f"rkdim{i}" for i in range(n)])
    await restrict_pool(db, champions, dimensions)
    fives = list(combinations(champions, 5))
    done = []
    for index in range(n):
        five = [c.champion_id for c in fives[index]]
        dimension = dimensions[index]
        anchor = await questions.materialize(
            db,
            patch.patch_id,
            Combination(PAIRWISE, five[0], champion_b=five[1], dimension_id=dimension.dimension_id),
        )
        ranking = Ranking(
            respondent_id=respondent.respondent_id,
            patch_id=patch.patch_id,
            dimension_id=dimension.dimension_id,
            anchor_question_id=anchor.question_id,
            champions=five,
        )
        db.add(ranking)
        await db.commit()
        await responses_service.record_ranking(
            db,
            respondent,
            ranking,
            anchor,
            None if not_sure(index) else five,
            4000,
            dt.datetime.now(dt.UTC),
        )
        done.append(ranking)
    return done


async def _extreme_question(db: AsyncSession, ranking: Ranking) -> Question:
    """La pregunta del primero contra el último del orden que contestó la persona."""
    assert ranking.submitted_order is not None
    low, high = sorted((ranking.submitted_order[0], ranking.submitted_order[-1]))
    return (
        await db.execute(
            sa.select(Question).where(
                Question.type == PAIRWISE,
                Question.champion_a == low,
                Question.champion_b == high,
                Question.dimension_id == ranking.dimension_id,
            )
        )
    ).scalar_one()


@requires_db
async def test_el_retest_del_tipo_1_es_el_par_de_las_puntas(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    """22 §4.1 — se repite el primero contra el último, como ancla de un ranking nuevo."""
    row, token = respondent
    done = await _rankings(db, patch, row, 16)
    await _due(db, row)
    http = as_respondent(client, token)

    item = (await http.get("/questions/next?count=1")).json()["questions"][0]

    # Posición 16, distancia 15: sólo califican los rankings de las posiciones 0 y 1.
    extremes = {(await _extreme_question(db, r)).question_id: r for r in done[:2]}
    assert item["question_id"] in extremes
    anchor = await db.get(Question, item["question_id"])
    assert anchor is not None
    shown = [c["id"] for c in item["champions"]]
    assert {anchor.champion_a, anchor.champion_b} <= set(shown)

    # Mismo sentido que la vez anterior: el que había quedado primero, arriba otra vez.
    original = extremes[item["question_id"]]
    assert original.submitted_order is not None
    first, last = original.submitted_order[0], original.submitted_order[-1]
    order = [first, *[c for c in shown if c not in (first, last)], last]
    posted = await http.post(
        "/responses",
        json={
            "question_id": item["question_id"],
            "ranking_id": item["ranking_id"],
            "answer": {"order": order},
            "response_time_ms": 7000,
        },
    )

    assert posted.status_code == 201
    first_row, repeat = await _rows_for(db, row.respondent_id, item["question_id"])
    assert repeat.is_retest_of == first_row.response_id
    assert repeat.ranking_id == item["ranking_id"]
    await db.refresh(row)
    assert (row.retest_pairs, row.retest_consistent) == (1, 1)
    assert row.answers_count == 17


@requires_db
async def test_un_ranking_not_sure_no_se_retestea(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    """§4 — repetir algo contestado `unknown` no mide nada: sin elegibles, va una común."""
    row, token = respondent
    done = await _rankings(db, patch, row, 16, not_sure=lambda i: i < 2)
    await _due(db, row)

    item = (await as_respondent(client, token).get("/questions/next?count=1")).json()[
        "questions"
    ][0]

    answered = {
        r.question_id
        for r in (
            await db.execute(sa.select(Response).where(Response.respondent_id == row.respondent_id))
        ).scalars()
    }
    assert item["question_id"] not in answered
    assert all(r.submitted_order is None for r in done[:2])
    await db.refresh(row)
    assert row.pending_retest_of is None
    assert row.next_retest_at == 16
