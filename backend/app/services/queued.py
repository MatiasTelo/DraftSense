"""La cola re-armada en otro idioma — `GET /questions/queued` ([ADR-029], `docs/12-api.md` §2.8).

Cuando la persona cambia de idioma, la tarjeta que está mirando tiene que seguir siendo la misma.
El servidor no puede volver a servirla por el sampler: no repite lo que el cliente tiene en cola, y
servirla otra vez movería posiciones y cadencias (ADR-020). Esto es `render()` sobre preguntas que
ya existen, y nada más.

**Sólo lee.** Si este módulo escribiera —una cadencia, un `exposure_count`, un ranking nuevo—, el
cambio de idioma alteraría qué honeypot o qué retest le toca a la persona, y la calidad dependería
de un botón de la interfaz. Hay un test que lo cuida.

[ADR-029]: ../../../docs/13-adr/ADR-029-cambiar-de-idioma-traduce-la-cola.md
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Champion, Dimension, Question, QuestionType, Ranking, Respondent, Response
from app.schemas.questions import QuestionOut
from app.services import questions
from app.services.question_texts import DEFAULT_LANG, Lang


async def rerender(
    session: AsyncSession,
    respondent: Respondent,
    ids: Sequence[int],
    lang: Lang = DEFAULT_LANG,
) -> list[QuestionOut]:
    """Las preguntas de `ids` armadas en `lang`, en ese orden, omitiendo las que no corresponden.

    Se omiten los ids que no existen, los ya contestados por este respondedor —salvo su retest
    pendiente, que repite una contestada a propósito— y, en el tipo 1, las anclas sin un ranking
    pendiente suyo. El parche no filtra: una respuesta en vuelo de un parche recién reemplazado se
    acepta (ADR-024), así que su pregunta también se traduce.
    """
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return []

    found = {
        q.question_id: q
        for q in (
            await session.execute(sa.select(Question).where(Question.question_id.in_(wanted)))
        ).scalars()
    }
    answered = set(
        (
            await session.execute(
                sa.select(Response.question_id).where(
                    Response.respondent_id == respondent.respondent_id,
                    Response.question_id.in_(wanted),
                )
            )
        ).scalars()
    )
    retest = await _pending_retest_question(session, respondent)
    rankings = await _pending_rankings(session, respondent, wanted)

    kept: list[Question] = []
    for question_id in wanted:
        question = found.get(question_id)
        if question is None:
            continue
        if question_id in answered and question_id != retest:
            continue
        if question.type is QuestionType.PAIRWISE_DIMENSION and question_id not in rankings:
            continue
        kept.append(question)
    if not kept:
        return []

    champion_ids = {
        c
        for q in kept
        for c in (q.champion_a, q.champion_b, q.champion_c, q.champion_d)
        if c is not None
    } | {c for r in rankings.values() for c in r.champions}
    champions = {
        c.champion_id: c
        for c in (
            await session.execute(sa.select(Champion).where(Champion.champion_id.in_(champion_ids)))
        ).scalars()
    }
    dimension_ids = {q.dimension_id for q in kept if q.dimension_id is not None}
    dimensions = {
        d.dimension_id: d
        for d in (
            await session.execute(
                sa.select(Dimension).where(Dimension.dimension_id.in_(dimension_ids))
            )
        ).scalars()
    }
    # El tipo 5 se arma con los atributos activos, igual que en el sampler: si el catálogo cambió
    # entre el servido y el cambio de idioma, la tarjeta muestra el vigente.
    traits = (
        await questions.active_traits(session)
        if any(q.type is QuestionType.TRAIT_MULTISELECT for q in kept)
        else []
    )
    return [
        questions.render(q, champions, dimensions, rankings.get(q.question_id), traits, lang)
        for q in kept
    ]


async def _pending_retest_question(session: AsyncSession, respondent: Respondent) -> int | None:
    """La pregunta del retest servido y no contestado, si hay uno (ADR-020)."""
    if respondent.pending_retest_of is None:
        return None
    original = await session.get(Response, respondent.pending_retest_of)
    return None if original is None else original.question_id


async def _pending_rankings(
    session: AsyncSession, respondent: Respondent, anchors: Sequence[int]
) -> dict[int, Ranking]:
    """El ranking pendiente **más reciente** de cada ancla.

    Puede haber dos con la misma ancla si el cliente descartó su cola con la versión anterior al
    cambiar de idioma (ADR-028 §5) y el sampler la volvió a servir; el que tiene en cola ahora es el
    último.
    """
    rows = await session.execute(
        sa.select(Ranking)
        .where(
            Ranking.respondent_id == respondent.respondent_id,
            Ranking.anchor_question_id.in_(list(anchors)),
            Ranking.submitted_order.is_(None),
        )
        .order_by(Ranking.ranking_id)
    )
    return {ranking.anchor_question_id: ranking for ranking in rows.scalars()}
