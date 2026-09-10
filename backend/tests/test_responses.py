"""Registro de respuestas — CA-201, CA-202, CA-204 y CA-209 de `03-criterios-aceptacion.md` §3.

**CA-205 (el retest sí se admite) no está cubierto y no puede estarlo todavía.** El request de
`docs/12-api.md` §2.4 no tiene campo para marcar una respuesta como repetición, y deducirlo en el
servidor haría que todo duplicado fuera un retest y que el 409 de CA-204 no ocurriera nunca. Quién
agenda los retests es el módulo de calidad de la semana 5; el criterio se cubre entonces.
"""

from __future__ import annotations

import datetime as dt

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Champion, Dimension, Patch, Question, QuestionType, Respondent, Response
from app.services import responses as responses_service
from tests.conftest import as_respondent, requires_db


async def _question(
    db: AsyncSession,
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension | None = None,
    question_type: QuestionType = QuestionType.PAIRWISE_DIMENSION,
) -> Question:
    """Una pregunta concreta, respetando el orden canónico y la forma de cada tipo."""
    low, high = sorted(c.champion_id for c in champions[:2])
    if question_type is QuestionType.PEAK_TIMING:
        row = Question(type=question_type, champion_a=low, patch_id=patch.patch_id)
    else:
        assert dimension is not None
        row = Question(
            type=question_type,
            champion_a=low,
            champion_b=high,
            dimension_id=dimension.dimension_id,
            patch_id=patch.patch_id,
        )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@requires_db
async def test_registro_correcto(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """CA-201 — se crea la fila con su answer, su tiempo, el tipo y el parche de la pregunta."""
    row, token = respondent
    question = await _question(db, patch, champions, dimension)

    response = await as_respondent(client, token).post(
        "/responses",
        json={
            "question_id": question.question_id,
            "answer": {"choice": "a"},
            "response_time_ms": 2140,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["recorded"] is True
    assert body["progress"]["answers_count"] == 1

    stored = (
        await db.execute(sa.select(Response).where(Response.question_id == question.question_id))
    ).scalar_one()
    assert stored.answer == {"choice": "a"}
    assert stored.response_time_ms == 2140
    assert stored.type is question.type
    assert stored.patch_id == patch.patch_id
    assert row.answers_count == 1


@requires_db
async def test_forma_invalida_rechazada(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
) -> None:
    """CA-202 — un `choice` contra una pregunta de `peak_timing` es 400, y no se crea nada."""
    _, token = respondent
    question = await _question(db, patch, champions, question_type=QuestionType.PEAK_TIMING)

    response = await as_respondent(client, token).post(
        "/responses",
        json={
            "question_id": question.question_id,
            "answer": {"choice": "a"},
            "response_time_ms": 900,
        },
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "answer_shape_mismatch"
    assert error["field"] == "answer"

    count = (
        await db.execute(
            sa.select(sa.func.count())
            .select_from(Response)
            .where(Response.question_id == question.question_id)
        )
    ).scalar_one()
    assert count == 0


@requires_db
async def test_respuesta_duplicada_rechazada(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """CA-204 — el 409 lo levanta el índice único parcial, no un SELECT previo."""
    _, token = respondent
    question = await _question(db, patch, champions, dimension)
    payload = {
        "question_id": question.question_id,
        "answer": {"choice": "b"},
        "response_time_ms": 1500,
    }

    first = await as_respondent(client, token).post("/responses", json=payload)
    assert first.status_code == 201

    second = await as_respondent(client, token).post("/responses", json=payload)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_response"


@requires_db
async def test_pregunta_inexistente(
    client: AsyncClient, respondent: tuple[Respondent, str]
) -> None:
    """`docs/12-api.md` §3 — `question_not_found`."""
    _, token = respondent
    response = await as_respondent(client, token).post(
        "/responses",
        json={"question_id": 999_999_999, "answer": {"choice": "a"}, "response_time_ms": 1000},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "question_not_found"


@requires_db
async def test_cabeceras_de_rate_limit(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """`docs/12-api.md` §4 — toda respuesta del endpoint las lleva."""
    _, token = respondent
    question = await _question(db, patch, champions, dimension)

    response = await as_respondent(client, token).post(
        "/responses",
        json={
            "question_id": question.question_id,
            "answer": {"choice": "a"},
            "response_time_ms": 1000,
        },
    )

    assert response.headers["X-RateLimit-Limit"] == str(responses_service.PER_MINUTE)
    assert response.headers["X-RateLimit-Remaining"] == str(responses_service.PER_MINUTE - 1)
    assert int(response.headers["X-RateLimit-Reset"]) > 0


@requires_db
async def test_limite_de_tasa(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CA-209 — al pasarse, 429 con `Retry-After`.

    El límite se baja a 2 en vez de escribir 40 respuestas: lo que se prueba es la lógica de la
    ventana deslizante, no el número, y el número ya está aserto en `test_cabeceras_de_rate_limit`.
    """
    monkeypatch.setattr(responses_service, "PER_MINUTE", 2)
    _, token = respondent
    http = as_respondent(client, token)

    for index in range(2):
        question = await _question(db, patch, champions[index:], dimension)
        ok = await http.post(
            "/responses",
            json={
                "question_id": question.question_id,
                "answer": {"choice": "a"},
                "response_time_ms": 1000,
            },
        )
        assert ok.status_code == 201

    extra = await _question(db, patch, champions[2:], dimension)
    blocked = await http.post(
        "/responses",
        json={
            "question_id": extra.question_id,
            "answer": {"choice": "a"},
            "response_time_ms": 1000,
        },
    )

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limit_exceeded"
    assert int(blocked.headers["Retry-After"]) >= 1


@requires_db
async def test_el_crudo_conserva_su_parche(
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """ADR-004 — `patch_id` se copia de la pregunta y nunca se pierde."""
    row, _ = respondent
    question = await _question(db, patch, champions, dimension)

    stored = await responses_service.record(
        db, row, question, {"choice": "unknown"}, 3000, dt.datetime.now(dt.UTC)
    )

    assert stored.patch_id == patch.patch_id
    assert stored.type is QuestionType.PAIRWISE_DIMENSION
