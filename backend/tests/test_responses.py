"""Registro de respuestas — CA-201, CA-202, CA-204 y CA-209 de `03-criterios-aceptacion.md` §3.

**CA-205 (el retest sí se admite) no está cubierto y no puede estarlo todavía.** El request de
`docs/12-api.md` §2.4 no tiene campo para marcar una respuesta como repetición, y deducirlo en el
servidor haría que todo duplicado fuera un retest y que el 409 de CA-204 no ocurriera nunca. Quién
agenda los retests es el módulo de calidad de la semana 5; el criterio se cubre entonces.
"""

from __future__ import annotations

import datetime as dt
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
    Respondent,
    Response,
)
from app.services import responses as responses_service
from tests.conftest import as_respondent, requires_db


async def _question(
    db: AsyncSession,
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension | None = None,
    question_type: QuestionType = QuestionType.PAIRWISE_DIMENSION,
    answer_counts: dict[str, int] | None = None,
) -> Question:
    """Una pregunta concreta, respetando el orden canónico y la forma de cada tipo.

    `answer_counts` permite fabricar el consenso sin escribir veinte respuestas: el feedback lee
    esa columna, no `responses`.
    """
    low, high = sorted(c.champion_id for c in champions[:2])
    counts = answer_counts or {}
    if question_type is QuestionType.PEAK_TIMING:
        row = Question(
            type=question_type, champion_a=low, patch_id=patch.patch_id, answer_counts=counts
        )
    elif question_type is QuestionType.LANE_MATCHUP:
        row = Question(
            type=question_type,
            champion_a=low,
            champion_b=high,
            role=LaneRole.MID,
            patch_id=patch.patch_id,
            answer_counts=counts,
        )
    else:
        assert dimension is not None
        row = Question(
            type=question_type,
            champion_a=low,
            champion_b=high,
            dimension_id=dimension.dimension_id,
            patch_id=patch.patch_id,
            answer_counts=counts,
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


# -------------------------------------------------------------------------- tipos 2 y 3


async def _post(
    client: AsyncClient, token: str, question: Question, answer: object
) -> dict[str, Any]:
    response = await as_respondent(client, token).post(
        "/responses",
        json={"question_id": question.question_id, "answer": answer, "response_time_ms": 4000},
    )
    return {"status": response.status_code, "body": response.json()}


async def _stored(db: AsyncSession, question: Question) -> list[Response]:
    statement = sa.select(Response).where(Response.question_id == question.question_id)
    return list((await db.execute(statement)).scalars())


@requires_db
async def test_registro_de_un_pico(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
) -> None:
    """CA-201 para el tipo 2 — el minuto se guarda tal cual, con el tipo de la pregunta."""
    _, token = respondent
    question = await _question(db, patch, champions, question_type=QuestionType.PEAK_TIMING)

    result = await _post(client, token, question, {"minute": 27})

    assert result["status"] == 201
    [stored] = await _stored(db, question)
    assert stored.answer == {"minute": 27}
    assert stored.type is QuestionType.PEAK_TIMING


@requires_db
async def test_registro_de_un_matchup(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
) -> None:
    _, token = respondent
    question = await _question(db, patch, champions, question_type=QuestionType.LANE_MATCHUP)

    result = await _post(client, token, question, {"choice": "a_slight"})

    assert result["status"] == 201
    [stored] = await _stored(db, question)
    assert stored.answer == {"choice": "a_slight"}
    assert stored.type is QuestionType.LANE_MATCHUP


@requires_db
@pytest.mark.parametrize("minute", [41, -1, 27.5, True, "27"])
async def test_forma_invalida_de_pico_rechazada(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    minute: object,
) -> None:
    """`docs/11-modelo-de-datos.md` §5 — entero entre 0 y 40. `true` no es el minuto 1."""
    _, token = respondent
    question = await _question(db, patch, champions, question_type=QuestionType.PEAK_TIMING)

    result = await _post(client, token, question, {"minute": minute})

    assert result["status"] == 400
    assert result["body"]["error"]["code"] == "answer_shape_mismatch"
    assert await _stored(db, question) == []


@requires_db
async def test_forma_invalida_de_matchup_rechazada(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
) -> None:
    """La escala del tipo 3 no admite las opciones del tipo 1."""
    _, token = respondent
    question = await _question(db, patch, champions, question_type=QuestionType.LANE_MATCHUP)

    result = await _post(client, token, question, {"choice": "a"})

    assert result["status"] == 400
    assert result["body"]["error"]["code"] == "answer_shape_mismatch"
    assert await _stored(db, question) == []


@requires_db
async def test_el_feedback_de_eleccion_no_lleva_claves_nulas(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """`docs/12-api.md` §2.4 — las claves del tipo 2 no viajan en `null` en los demás tipos."""
    _, token = respondent
    question = await _question(
        db, patch, champions, dimension, answer_counts={"a": 15, "b": 4, "unknown": 1}
    )

    result = await _post(client, token, question, {"choice": "a"})

    assert set(result["body"]["feedback"]) == {"consensus", "agreed_with_majority", "sample_size"}


@requires_db
async def test_el_feedback_del_pico_tiene_la_forma_del_contrato(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
) -> None:
    """`docs/12-api.md` §2.4, literal: `{consensus_median, your_answer, sample_size}`."""
    _, token = respondent
    question = await _question(
        db,
        patch,
        champions,
        question_type=QuestionType.PEAK_TIMING,
        answer_counts={"25": 5, "26": 6, "27": 5, "30": 4},
    )

    result = await _post(client, token, question, {"minute": 27})

    assert result["body"]["feedback"] == {
        "consensus_median": 26,
        "your_answer": 27,
        "sample_size": 20,
    }


@requires_db
async def test_sin_soporte_el_feedback_es_null_explicito(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
) -> None:
    """Omitir claves vale adentro del feedback; el feedback ausente se dice con `null`."""
    _, token = respondent
    question = await _question(
        db, patch, champions, question_type=QuestionType.PEAK_TIMING, answer_counts={"20": 3}
    )

    result = await _post(client, token, question, {"minute": 20})

    assert "feedback" in result["body"]
    assert result["body"]["feedback"] is None
