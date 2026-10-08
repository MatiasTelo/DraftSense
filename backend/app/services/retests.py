"""Test-retest: qué se repite y qué cuenta como consistente (`docs/22-calidad-de-datos.md` §4).

El retest mide si alguien contesta al azar, no si se acuerda de lo que dijo. Por eso la tolerancia
de los tipos 2 y 3 es deliberada: «gana Darius fuerte» y quince preguntas después «gana Darius
apenas» es la misma opinión.

Cómo se marca que una respuesta es un retest está en ADR-020: lo sabe el servidor, nunca el
cliente.
"""

from __future__ import annotations

import random
from collections.abc import Collection
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Question, QuestionType, Respondent, Response
from app.services.answers import LANE_OUTCOME, UNKNOWN_CHOICE
from app.services.questions import Space

UNKNOWN: Final = UNKNOWN_CHOICE

#: Tipo 2: dos minutos que difieren en esto o menos son la misma respuesta (§4).
PEAK_TOLERANCE_MINUTES: Final = 5


def is_consistent(
    question_type: QuestionType, original: dict[str, Any], repeat: dict[str, Any]
) -> bool | None:
    """Si el par es consistente, o `None` si el par no cuenta.

    - Tipo 1: la opción idéntica. `unknown` en cualquiera de las dos anula el par.
    - Tipo 3: del mismo lado, o las dos `even`. *Wins hard* contra *wins slightly* del mismo
      campeón es consistente.
    - Tipo 2: minutos a 5 o menos de distancia.

    Los tipos 4 y 5 se sirven desde la semana 8 y entran con ellos: el 5 necesita decidir qué
    Jaccard tienen dos listas vacías, que §4 no dice.
    """
    match question_type:
        case QuestionType.PAIRWISE_DIMENSION:
            first, second = original.get("choice"), repeat.get("choice")
            if UNKNOWN in (first, second):
                return None
            return bool(first == second)
        case QuestionType.LANE_MATCHUP:
            return LANE_OUTCOME[original["choice"]] == LANE_OUTCOME[repeat["choice"]]
        case QuestionType.PEAK_TIMING:
            gap = abs(int(original["minute"]) - int(repeat["minute"]))
            return gap <= PEAK_TOLERANCE_MINUTES
        case _:
            return None


async def pick_eligible(
    session: AsyncSession,
    respondent: Respondent,
    patch_id: int,
    space: Space,
    position: int,
    min_distance: int,
    served_types: Collection[QuestionType],
    rng: random.Random,
) -> tuple[Response, Question] | None:
    """Una respuesta original al azar entre las elegibles para repetir en `position`.

    Elegible, según lo acordado en §4: no es un retest ni una honeypot, no es `unknown`, está a
    `min_distance` posiciones o más, es de una pregunta del parche vigente que el pool actual
    todavía admite, y nunca se retesteó.

    La distancia se cuenta en posiciones, no en tiempo. Las respuestas del respondedor ocupan las
    posiciones `0 … answers_count - 1` en orden de creación; las que están a menos de
    `min_distance` de `position` son las más recientes, y se saltean con un `OFFSET` sobre
    `responses_by_respondent` para encontrar la última que sí califica.
    """
    newest_allowed = position - min_distance
    if newest_allowed < 0:
        return None
    skip = max(0, respondent.answers_count - 1 - newest_allowed)
    cutoff = (
        await session.execute(
            sa.select(Response.created_at, Response.response_id)
            .where(Response.respondent_id == respondent.respondent_id)
            .order_by(Response.created_at.desc(), Response.response_id.desc())
            .offset(skip)
            .limit(1)
        )
    ).first()
    if cutoff is None:
        return None

    repeated = aliased(Response)
    rows = await session.execute(
        sa.select(Response, Question)
        .join(Question, Question.question_id == Response.question_id)
        .where(
            Response.respondent_id == respondent.respondent_id,
            Response.is_retest_of.is_(None),
            ~Question.is_honeypot,
            Question.patch_id == patch_id,
            Response.type.in_(list(served_types)),
            # El tipo 2 no tiene `choice`: sin el COALESCE, `NULL <> 'unknown'` lo descartaría.
            sa.func.coalesce(Response.answer["choice"].astext, "") != UNKNOWN,
            sa.tuple_(Response.created_at, Response.response_id)
            <= sa.tuple_(sa.literal(cutoff.created_at), sa.literal(cutoff.response_id)),
            ~sa.exists().where(
                repeated.respondent_id == Response.respondent_id,
                repeated.is_retest_of == Response.response_id,
            ),
        )
        # Orden fijo para que el sorteo sea reproducible con una semilla.
        .order_by(Response.response_id)
    )
    candidates = [
        (response, question)
        for response, question in rows.tuples()
        if space.admits(question)
    ]
    if not candidates:
        return None
    return rng.choice(candidates)
