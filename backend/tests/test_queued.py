"""La cola re-armada en otro idioma — CA-109, `docs/12-api.md` §2.8 y ADR-029.

Lo que más importa probar no es la traducción —eso ya lo cubre CA-107— sino que **el endpoint no
toca nada**: ni cadencias, ni `exposure_count`, ni rankings. Si lo hiciera, cambiar de idioma
alteraría qué honeypot o qué retest le toca a la persona.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Patch, Question, QuestionType, Ranking, Respondent
from app.services import question_texts
from app.services import sampler as sampler_service
from app.services.questions import Variant
from tests.conftest import (
    FAR,
    add_response,
    as_respondent,
    make_champions,
    make_dimensions,
    pairwise_question,
    requires_db,
    restrict_pool,
)

ES = question_texts.texts("es")


async def _setup(db: AsyncSession, patch: Patch, respondent: Respondent) -> None:
    champions = await make_champions(db, patch, 10, prefix="Qd")
    [dimension] = await make_dimensions(db, ["qdim"])
    dimension.prompt_es = "¿Quién tiene más qdim?"
    await restrict_pool(db, champions, [dimension])
    # Pasadas las tres primeras de tipo 1 (CA-102) y sin honeypots ni retests a la vista.
    respondent.answers_count = 3
    respondent.next_honeypot_at = FAR
    respondent.next_retest_at = FAR
    await db.commit()


async def _snapshot(db: AsyncSession, respondent: Respondent) -> dict[str, Any]:
    """Todo lo que el sampler mueve al servir: si el endpoint lo tocara, cambiaría."""
    await db.refresh(respondent)
    exposures = (
        await db.execute(
            sa.select(Question.question_id, Question.exposure_count).order_by(Question.question_id)
        )
    ).all()
    rankings = (await db.execute(sa.select(sa.func.count()).select_from(Ranking))).scalar_one()
    return {
        "answers_count": respondent.answers_count,
        "next_honeypot_at": respondent.next_honeypot_at,
        "next_retest_at": respondent.next_retest_at,
        "pending_honeypot": respondent.pending_honeypot,
        "pending_retest_of": respondent.pending_retest_of,
        "exposures": exposures,
        "rankings": rankings,
    }


@requires_db
async def test_ca109_la_cola_se_traduce_sin_tocar_el_sampler(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row, token = respondent
    await _setup(db, patch, row)
    http = as_respondent(client, token)

    monkeypatch.setattr(sampler_service, "TYPE_WEIGHTS", {Variant.PAIRWISE: 1})
    [ranking] = (await http.get("/questions/next?count=1")).json()["questions"]
    monkeypatch.setattr(sampler_service, "TYPE_WEIGHTS", {Variant.PEAK: 1})
    [peak] = (await http.get(f"/questions/next?count=1&queued={ranking['question_id']}")).json()[
        "questions"
    ]
    assert ranking["prompt"] == "Who has more qdim?"
    before = await _snapshot(db, row)

    response = await http.get(
        f"/questions/queued?ids={ranking['question_id']},{peak['question_id']}&lang=es"
    )

    assert response.status_code == 200
    first, second = response.json()["questions"]
    # El mismo ranking, con los cinco en el mismo orden, y en español.
    assert first["question_id"] == ranking["question_id"]
    assert first["ranking_id"] == ranking["ranking_id"]
    assert first["champions"] == ranking["champions"]
    assert first["prompt"] == "¿Quién tiene más qdim?"
    assert first["unknown_label"] == ES.unknown_label
    assert second["question_id"] == peak["question_id"]
    assert second["type"] == "peak_timing"
    assert second["prompt"] != peak["prompt"]
    # Y nada se movió.
    assert await _snapshot(db, row) == before

    # El orden es el pedido, y en inglés vuelve a ser lo que se sirvió.
    english = (
        await http.get(f"/questions/queued?ids={peak['question_id']},{ranking['question_id']}")
    ).json()["questions"]
    assert english == [peak, ranking]


@requires_db
async def test_se_omite_lo_que_no_corresponde(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
) -> None:
    row, token = respondent
    await _setup(db, patch, row)
    champions = await make_champions(db, patch, 3, prefix="Om")
    [dimension] = await make_dimensions(db, ["qdim"])

    answered = Question(
        type=QuestionType.PEAK_TIMING, champion_a=champions[0].champion_id, patch_id=patch.patch_id
    )
    retested = Question(
        type=QuestionType.PEAK_TIMING, champion_a=champions[1].champion_id, patch_id=patch.patch_id
    )
    db.add_all([answered, retested])
    await db.commit()
    await add_response(db, row, answered, {"minute": 20})
    original = await add_response(db, row, retested, {"minute": 25})
    # El retest servido repite una contestada a propósito: ésa sí vuelve (ADR-020).
    row.pending_retest_of = original.response_id
    # Un ancla de tipo 1 sin ranking pendiente de este respondedor no se puede armar.
    orphan = await pairwise_question(db, patch, champions[1], champions[2], dimension)
    await db.commit()

    ids = [answered.question_id, 999_999_999, orphan.question_id, retested.question_id]
    response = await as_respondent(client, token).get(
        "/questions/queued?ids=" + ",".join(map(str, ids))
    )

    assert response.status_code == 200
    assert [q["question_id"] for q in response.json()["questions"]] == [retested.question_id]


@requires_db
@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("", "ids"),
        ("?ids=", "ids"),
        ("?ids=1,x", "ids"),
        ("?ids=" + ",".join(str(i) for i in range(1, 12)), "ids"),
        ("?ids=1&lang=fr", "lang"),
    ],
)
async def test_los_parametros_invalidos_son_400(
    client: AsyncClient,
    respondent: tuple[Respondent, str],
    query: str,
    field: str,
) -> None:
    _, token = respondent
    response = await as_respondent(client, token).get(f"/questions/queued{query}")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_parameter"
    assert response.json()["error"]["field"] == field
