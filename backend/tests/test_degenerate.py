"""Patrones degenerados — CA-304 y CA-305 de `03-criterios-aceptacion.md` §4.

Cómo se cuenta el *straightlining* está en la nota del 16/09 de `22-calidad-de-datos.md` §5.2:
por tipo, sobre la clave de la opción, con `unknown` cortando la racha, y un tramo largo como una
sola racha. Desde el 08/10 el tipo 1 quedó afuera: es un ranking sin posición (ADR-022).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Dimension,
    LaneRole,
    Patch,
    Question,
    QuestionType,
    Ranking,
    Respondent,
    Response,
)
from app.services import degenerate, sessions
from app.services import questions as questions_service
from app.services import responses as responses_service
from app.services.degenerate import HistoryRow, count, straightline_runs
from app.services.questions import Combination
from tests.conftest import add_response, make_champions, pairwise_question, requires_db

PAIRWISE = QuestionType.PAIRWISE_DIMENSION
PEAK = QuestionType.PEAK_TIMING
LANE = QuestionType.LANE_MATCHUP


def _row(question_type: QuestionType, answer: dict[str, Any], elapsed: int = 2000) -> HistoryRow:
    return HistoryRow(type=question_type, answer=answer, response_time_ms=elapsed)


# ------------------------------------------------------------------------------ sin base de datos


def test_ocho_seguidas_en_la_misma_posicion_son_una_racha() -> None:
    assert straightline_runs(["a"] * 8, 8) == 1


def test_siete_no_alcanzan() -> None:
    assert straightline_runs(["b"] * 7, 8) == 0


def test_un_tramo_largo_es_una_sola_racha() -> None:
    """§5.2, nota del 16/09 — dieciséis seguidas no son dos rachas."""
    assert straightline_runs(["a"] * 16, 8) == 1


def test_dos_tramos_separados_son_dos_rachas() -> None:
    assert straightline_runs(["a"] * 8 + ["b"] + ["a"] * 8, 8) == 2


def test_unknown_corta_la_racha() -> None:
    assert straightline_runs(["a"] * 4 + ["unknown"] + ["a"] * 4, 8) == 0


def test_unknown_no_forma_racha_propia() -> None:
    """Ocho *Not sure* seguidos son la respuesta honesta de quien no conoce a esos campeones."""
    assert straightline_runs(["unknown"] * 20, 8) == 0


def test_la_racha_se_cuenta_dentro_de_cada_tipo() -> None:
    """La regla de variedad impide 8 seguidas del mismo tipo: la racha se busca por tipo."""
    rows: list[HistoryRow] = []
    for _ in range(8):
        rows.append(_row(LANE, {"choice": "a_slight"}))
        rows.append(_row(PEAK, {"minute": 20}))
    assert count(rows, 800, 8) == (0, 1)


def test_el_tipo_1_ya_no_tiene_posicion() -> None:
    """22 §5.2, cambio del 08/10 — el ranking llega en orden aleatorio y se ordena arrastrando."""
    rows = [_row(PAIRWISE, {"choice": "a"}) for _ in range(20)]
    assert count(rows, 800, 8) == (0, 0)


def test_el_tipo_2_no_tiene_posicion() -> None:
    rows = [_row(PEAK, {"minute": 20}) for _ in range(20)]
    assert count(rows, 800, 8) == (0, 0)


def test_el_tipo_3_cuenta_por_nivel_de_la_escala() -> None:
    rows = [_row(LANE, {"choice": "even"}) for _ in range(8)]
    assert count(rows, 800, 8) == (0, 1)
    mixed = [_row(LANE, {"choice": c}) for c in ["a_strong", "a_slight"] * 4]
    assert count(mixed, 800, 8) == (0, 0)


def test_apurada_es_estrictamente_menos_de_800() -> None:
    rows = [_row(PAIRWISE, {"choice": "a"}, 799), _row(PAIRWISE, {"choice": "b"}, 800)]
    assert count(rows, 800, 8) == (1, 0)


# ------------------------------------------------------------------------------- con base de datos


async def _questions(
    db: AsyncSession, patch: Patch, dimension: Dimension, n: int
) -> list[Question]:
    """Preguntas de tipo 3: desde el 08/10 es el único tipo con *straightlining* (ADR-022)."""
    pool = await make_champions(db, patch, 6, prefix="Deg")
    pairs = [(a, b) for i, a in enumerate(pool) for b in pool[i + 1 :]]
    return [
        await questions_service.materialize(
            db,
            patch.patch_id,
            Combination(LANE, *sorted((a.champion_id, b.champion_id)), role=LaneRole.MID),
        )
        for a, b in pairs[:n]
    ]


async def _respondent(db: AsyncSession, tag: str) -> Respondent:
    row, _ = await sessions.create(db, f"huella-degenerada-{tag}")
    return row


@requires_db
async def test_ca304_una_apurada_sube_el_contador_y_recalcula_el_trust(
    db: AsyncSession, patch: Patch, dimension: Dimension
) -> None:
    questions = await _questions(db, patch, dimension, 2)
    respondent = await _respondent(db, "apurada")
    await add_response(
        db, respondent, questions[0], {"choice": "a_slight"}, response_time_ms=450
    )
    await add_response(
        db, respondent, questions[1], {"choice": "b_slight"}, response_time_ms=2400
    )

    result = await degenerate.detect(db)

    await db.refresh(respondent)
    assert result.respondents >= 1
    assert respondent.fast_answers == 1
    # d = 1 / 20: el trust baja de 0.500 a 0.5 · (1 - 0.5 · 0.05).
    assert respondent.trust_score == Decimal("0.488")


@requires_db
async def test_ca305_ocho_en_la_misma_posicion_marcan_la_racha(
    db: AsyncSession, patch: Patch, dimension: Dimension
) -> None:
    questions = await _questions(db, patch, dimension, 8)
    respondent = await _respondent(db, "racha")
    for question in questions:
        await add_response(db, respondent, question, {"choice": "a_slight"})

    await degenerate.detect(db)

    await db.refresh(respondent)
    assert respondent.straightline_runs == 1
    assert respondent.trust_score < Decimal("0.500")


@requires_db
async def test_correrlo_dos_veces_no_duplica_nada(
    db: AsyncSession, patch: Patch, dimension: Dimension
) -> None:
    """Recalcula desde cero (nota del 16/09 en §5): la segunda corrida no cambia nada."""
    questions = await _questions(db, patch, dimension, 8)
    respondent = await _respondent(db, "idempotente")
    for question in questions:
        await add_response(
            db, respondent, question, {"choice": "b_slight"}, response_time_ms=300
        )

    await degenerate.detect(db)
    await db.refresh(respondent)
    first = (respondent.fast_answers, respondent.straightline_runs, respondent.trust_score)
    second_run = await degenerate.detect(db)
    await db.refresh(respondent)

    assert first == (8, 1, respondent.trust_score)
    assert (respondent.fast_answers, respondent.straightline_runs) == (8, 1)
    assert second_run.changed == 0


@requires_db
async def test_ninguna_respuesta_se_toca(
    db: AsyncSession, patch: Patch, dimension: Dimension
) -> None:
    questions = await _questions(db, patch, dimension, 3)
    respondent = await _respondent(db, "intacta")
    for question in questions:
        await add_response(
            db, respondent, question, {"choice": "a_slight"}, response_time_ms=100
        )

    await degenerate.detect(db)

    stored = (
        await db.execute(
            sa.select(sa.func.count())
            .select_from(Response)
            .where(Response.respondent_id == respondent.respondent_id)
        )
    ).scalar_one()
    assert stored == 3


@requires_db
async def test_un_ranking_apurado_es_una_sola_respuesta_apurada(
    db: AsyncSession, patch: Patch, dimension: Dimension
) -> None:
    """ADR-022 — las diez filas comparten el tiempo, pero la persona tocó una sola vez."""
    five = await make_champions(db, patch, 5, prefix="Rkdeg")
    ids = [c.champion_id for c in five]
    respondent = await _respondent(db, "ranking")
    anchor = await pairwise_question(db, patch, five[0], five[1], dimension)
    ranking = Ranking(
        respondent_id=respondent.respondent_id,
        patch_id=patch.patch_id,
        dimension_id=dimension.dimension_id,
        anchor_question_id=anchor.question_id,
        champions=ids,
    )
    db.add(ranking)
    await db.commit()
    await responses_service.record_ranking(
        db, respondent, ranking, anchor, ids, 500, dt.datetime.now(dt.UTC)
    )

    await degenerate.detect(db)

    await db.refresh(respondent)
    assert respondent.fast_answers == 1
