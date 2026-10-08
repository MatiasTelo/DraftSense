"""Registro de respuestas — CA-201 a CA-213 de `03-criterios-aceptacion.md` §3.

Desde el 08/10 el tipo 1 es un ranking de cinco que se guarda como diez filas (ADR-022): los
criterios genéricos se prueban con el tipo 3, y el ranking tiene su propia sección al final.

CA-205 (el retest sí se admite) está en `test_retests.py`: desde la semana 5 el retest lo marca el
servidor al servirlo (ADR-020), así que se prueba junto con el sampler que lo agenda.
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
    Ranking,
    Respondent,
    Response,
)
from app.services import rankings, sessions
from app.services import responses as responses_service
from tests.conftest import add_response, as_respondent, pairwise_question, requires_db


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
    question = await _question(db, patch, champions, question_type=QuestionType.LANE_MATCHUP)

    response = await as_respondent(client, token).post(
        "/responses",
        json={
            "question_id": question.question_id,
            "answer": {"choice": "a_slight"},
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
    assert stored.answer == {"choice": "a_slight"}
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
    question = await _question(db, patch, champions, question_type=QuestionType.LANE_MATCHUP)
    payload = {
        "question_id": question.question_id,
        "answer": {"choice": "b_slight"},
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
    question = await _question(db, patch, champions, question_type=QuestionType.LANE_MATCHUP)

    response = await as_respondent(client, token).post(
        "/responses",
        json={
            "question_id": question.question_id,
            "answer": {"choice": "even"},
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
        question = await _question(
            db, patch, champions[index:], question_type=QuestionType.LANE_MATCHUP
        )
        ok = await http.post(
            "/responses",
            json={
                "question_id": question.question_id,
                "answer": {"choice": "even"},
                "response_time_ms": 1000,
            },
        )
        assert ok.status_code == 201

    extra = await _question(db, patch, champions[2:], question_type=QuestionType.LANE_MATCHUP)
    blocked = await http.post(
        "/responses",
        json={
            "question_id": extra.question_id,
            "answer": {"choice": "even"},
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
        db,
        patch,
        champions,
        question_type=QuestionType.LANE_MATCHUP,
        answer_counts={"a_slight": 15, "b_slight": 4, "even": 1},
    )

    result = await _post(client, token, question, {"choice": "a_slight"})

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


# ------------------------------------------------------------- tipo 1: el ranking de cinco


async def _ranking(
    db: AsyncSession,
    respondent: Respondent,
    patch: Patch,
    five: list[Champion],
    dimension: Dimension,
    anchor: Question | None = None,
) -> tuple[Ranking, Question]:
    """Un ranking servido a este respondedor con los cinco primeros, y su par inicial como ancla."""
    five = five[:5]
    if anchor is None:
        anchor = await pairwise_question(db, patch, five[0], five[1], dimension)
    ranking = Ranking(
        respondent_id=respondent.respondent_id,
        patch_id=patch.patch_id,
        dimension_id=dimension.dimension_id,
        anchor_question_id=anchor.question_id,
        champions=[c.champion_id for c in reversed(five)],
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)
    return ranking, anchor


def _order(five: list[Champion]) -> dict[str, list[int]]:
    """El orden de los cinco primeros tal como vienen: el primero es el que más tiene."""
    return {"order": [c.champion_id for c in five[:5]]}


async def _send(
    client: AsyncClient, token: str, ranking: Ranking, anchor: Question, answer: object
) -> Any:
    return await as_respondent(client, token).post(
        "/responses",
        json={
            "question_id": anchor.question_id,
            "ranking_id": ranking.ranking_id,
            "answer": answer,
            "response_time_ms": 9000,
        },
    )


async def _rows(db: AsyncSession, ranking: Ranking) -> list[Response]:
    statement = sa.select(Response).where(Response.ranking_id == ranking.ranking_id)
    return list((await db.execute(statement)).scalars())


async def _pairs(db: AsyncSession, rows: list[Response]) -> dict[tuple[int, int], str]:
    found: dict[tuple[int, int], str] = {}
    for stored in rows:
        question = await db.get(Question, stored.question_id)
        assert question is not None and question.champion_b is not None
        found[(question.champion_a, question.champion_b)] = stored.answer["choice"]
    return found


@requires_db
async def test_ca210_un_ranking_produce_diez_comparaciones(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    ranking_pool: list[Champion],
    dimension: Dimension,
) -> None:
    """CA-210 — diez filas canónicas con el mismo `ranking_id`, y la persona suma una respuesta."""
    row, token = respondent
    ranking, anchor = await _ranking(db, row, patch, ranking_pool, dimension)
    order = _order(ranking_pool)["order"]

    response = await _send(client, token, ranking, anchor, {"order": order})

    assert response.status_code == 201
    assert response.json()["progress"]["answers_count"] == 1
    rows = await _rows(db, ranking)
    assert len(rows) == 10
    assert {r.type for r in rows} == {QuestionType.PAIRWISE_DIMENSION}
    assert {r.response_time_ms for r in rows} == {9000}
    position = {champion: index for index, champion in enumerate(order)}
    assert await _pairs(db, rows) == {
        (low, high): "a" if position[low] < position[high] else "b"
        for low, high in rankings.pairs(order)
    }
    await db.refresh(ranking)
    assert ranking.submitted_order == order


@requires_db
async def test_ca211_un_par_ya_contestado_se_ignora(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    ranking_pool: list[Champion],
    dimension: Dimension,
) -> None:
    """CA-211 — la respuesta vieja queda como estaba y se guardan los otros nueve pares."""
    row, token = respondent
    earlier = await pairwise_question(db, patch, ranking_pool[3], ranking_pool[4], dimension)
    old = await add_response(db, row, earlier, {"choice": "a"})
    ranking, anchor = await _ranking(db, row, patch, ranking_pool, dimension)

    response = await _send(client, token, ranking, anchor, _order(ranking_pool))

    assert response.status_code == 201
    rows = await _rows(db, ranking)
    assert len(rows) == 9
    assert earlier.question_id not in {r.question_id for r in rows}
    kept = (
        (await db.execute(sa.select(Response).where(Response.question_id == earlier.question_id)))
        .scalars()
        .all()
    )
    assert [r.response_id for r in kept] == [old.response_id]


@requires_db
@pytest.mark.parametrize(
    "mutate",
    [
        lambda o: o[:4],
        lambda o: [*o[:4], o[0]],
        lambda o: [*o[:4], 999_999],
        lambda o: [str(c) for c in o],
    ],
    ids=["falta-uno", "repetido", "ajeno", "texto"],
)
async def test_ca212_el_orden_tiene_que_ser_el_del_ranking(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    ranking_pool: list[Champion],
    dimension: Dimension,
    mutate: Any,
) -> None:
    """CA-212 — un orden que no es permutación de los cinco es 400 y no crea nada."""
    row, token = respondent
    ranking, anchor = await _ranking(db, row, patch, ranking_pool, dimension)

    response = await _send(
        client, token, ranking, anchor, {"order": mutate(_order(ranking_pool)["order"])}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "answer_shape_mismatch"
    assert await _rows(db, ranking) == []


@requires_db
async def test_ca213_not_sure_vale_para_el_ranking_entero(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    ranking_pool: list[Champion],
    dimension: Dimension,
) -> None:
    """CA-213 — diez `unknown`, una respuesta, sin orden guardado y sin feedback."""
    row, token = respondent
    ranking, anchor = await _ranking(db, row, patch, ranking_pool, dimension)

    response = await _send(client, token, ranking, anchor, {"choice": "unknown"})

    assert response.status_code == 201
    assert response.json()["feedback"] is None
    assert response.json()["progress"]["answers_count"] == 1
    rows = await _rows(db, ranking)
    assert len(rows) == 10
    assert {r.answer["choice"] for r in rows} == {"unknown"}
    await db.refresh(ranking)
    assert ranking.submitted_order is None


@requires_db
async def test_el_ranking_tiene_que_ser_del_respondedor_y_de_esa_pregunta(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    ranking_pool: list[Champion],
    dimension: Dimension,
) -> None:
    """`docs/12-api.md` §3 — `ranking_not_found` si falta, si es ajeno o si el ancla no coincide."""
    row, token = respondent
    ranking, anchor = await _ranking(db, row, patch, ranking_pool, dimension)
    other = await pairwise_question(db, patch, ranking_pool[2], ranking_pool[3], dimension)
    stranger, _ = await sessions.create(db, "otra-huella")
    foreign, _ = await _ranking(db, stranger, patch, ranking_pool, dimension, anchor=anchor)
    order = _order(ranking_pool)

    missing = await as_respondent(client, token).post(
        "/responses",
        json={"question_id": anchor.question_id, "answer": order, "response_time_ms": 900},
    )
    wrong_anchor = await _send(client, token, ranking, other, order)
    not_mine = await _send(client, token, foreign, anchor, order)

    for response in (missing, wrong_anchor, not_mine):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "ranking_not_found"
        assert response.json()["error"]["field"] == "ranking_id"


@requires_db
async def test_reenviar_el_mismo_ranking_es_un_duplicado(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    ranking_pool: list[Champion],
    dimension: Dimension,
) -> None:
    """CA-204 para el ranking — el ancla ya contestada es 409 y no se agrega ninguna fila."""
    row, token = respondent
    ranking, anchor = await _ranking(db, row, patch, ranking_pool, dimension)
    ranking_id = ranking.ranking_id

    assert (await _send(client, token, ranking, anchor, _order(ranking_pool))).status_code == 201
    again = await _send(client, token, ranking, anchor, _order(ranking_pool))

    assert again.status_code == 409
    assert again.json()["error"]["code"] == "duplicate_response"
    # La API y el test comparten la sesión: el 409 la dejó a la espera de un rollback.
    await db.rollback()
    stored = await db.execute(sa.select(Response).where(Response.ranking_id == ranking_id))
    assert len(stored.scalars().all()) == 10


@requires_db
async def test_ca507_el_feedback_es_por_pares(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    ranking_pool: list[Champion],
    dimension: Dimension,
) -> None:
    """CA-507 — cuentan sólo los pares con soporte; el feedback dice en cuántos coincide."""
    row, token = respondent
    ranking, anchor = await _ranking(db, row, patch, ranking_pool, dimension)
    order = _order(ranking_pool)["order"]
    said = rankings.choices_from_order(order)
    by_id = {c.champion_id: c for c in ranking_pool}
    # El ancla y otros dos pares con soporte: coincide en los dos primeros y no en el tercero.
    supported = [
        (anchor.champion_a, anchor.champion_b),
        *[pair for pair in said if pair != (anchor.champion_a, anchor.champion_b)][:2],
    ]
    for index, (low, high) in enumerate(supported):
        assert high is not None
        question = (
            anchor
            if index == 0
            else await pairwise_question(db, patch, by_id[low], by_id[high], dimension)
        )
        flipped = "b" if said[(low, high)] == "a" else "a"
        majority = said[(low, high)] if index < 2 else flipped
        question.answer_counts = {majority: 25, "unknown": 1}
    await db.commit()

    response = await _send(client, token, ranking, anchor, {"order": order})

    assert response.json()["feedback"] == {
        "pairs_agreed": 2,
        "pairs_compared": 3,
        "sample_size": 78,
    }


@requires_db
async def test_sin_pares_con_soporte_el_feedback_del_ranking_es_null(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    ranking_pool: list[Champion],
    dimension: Dimension,
) -> None:
    """RF-114 — sin ningún par con 20 respuestas, la interfaz muestra el mensaje de los primeros."""
    row, token = respondent
    ranking, anchor = await _ranking(db, row, patch, ranking_pool, dimension)

    response = await _send(client, token, ranking, anchor, _order(ranking_pool))

    assert response.json()["feedback"] is None


@requires_db
async def test_el_rate_limit_cuenta_el_ranking_como_un_envio(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    ranking_pool: list[Champion],
    dimension: Dimension,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-022 — diez filas no son diez respuestas: con un límite de 2, el ranking deja lugar."""
    monkeypatch.setattr(responses_service, "PER_MINUTE", 2)
    row, token = respondent
    ranking, anchor = await _ranking(db, row, patch, ranking_pool, dimension)
    first = await _send(client, token, ranking, anchor, _order(ranking_pool))
    assert first.status_code == 201

    lane = await _question(db, patch, ranking_pool, question_type=QuestionType.LANE_MATCHUP)
    result = await _post(client, token, lane, {"choice": "even"})

    assert result["status"] == 201


@requires_db
async def test_un_par_no_ancla_que_es_honeypot_no_se_guarda(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    ranking_pool: list[Champion],
    dimension: Dimension,
) -> None:
    """22 §3.7 — una honeypot sólo se contesta como ancla y con su cadencia."""
    row, token = respondent
    trap = await pairwise_question(
        db,
        patch,
        ranking_pool[2],
        ranking_pool[3],
        dimension,
        is_honeypot=True,
        expected_answer={"choice": "a"},
    )
    ranking, anchor = await _ranking(db, row, patch, ranking_pool, dimension)

    await _send(client, token, ranking, anchor, _order(ranking_pool))

    rows = await _rows(db, ranking)
    assert len(rows) == 9
    assert trap.question_id not in {r.question_id for r in rows}
    await db.refresh(row)
    assert row.honeypot_attempts == 0
