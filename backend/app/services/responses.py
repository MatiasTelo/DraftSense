"""Registro de respuestas: rate limit, inserción append-only y feedback de consenso.

Es el camino crítico del sistema (`docs/10-arquitectura.md` §3) y tiene 150 ms de presupuesto.
Nada de lo que hace agrega: cuenta filas sobre índices e inserta una.

Lo que **no** hace en la semana 2, y hay que saberlo al leerlo: no evalúa honeypots, no marca
retests y no recalcula el trust score. Ese es el módulo de calidad de la semana 5
(`docs/22-calidad-de-datos.md`); el paso 5 de la arquitectura queda pendiente hasta entonces.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Question, Respondent, Response
from app.schemas.responses import Feedback, Progress
from app.services import app_settings, streaks

#: Los dos límites del contrato (`docs/12-api.md` §4). Son holgados para una persona —una
#: respuesta cada 5 a 10 segundos son unas 10 por minuto— y cortan el scripting trivial.
PER_MINUTE = 40
PER_DAY = 1500


class RateLimitError(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"retry after {retry_after}s")
        self.retry_after = retry_after


@dataclass(slots=True)
class RateLimitState:
    """Lo que viaja en las cabeceras `X-RateLimit-*` de toda respuesta del endpoint."""

    limit: int
    remaining: int
    reset: int


async def _count_since(
    session: AsyncSession, respondent: Respondent, since: dt.datetime
) -> int:
    return (
        await session.execute(
            sa.select(sa.func.count())
            .select_from(Response)
            .where(
                Response.respondent_id == respondent.respondent_id,
                Response.created_at > since,
            )
        )
    ).scalar_one()


async def check_rate_limit(
    session: AsyncSession, respondent: Respondent, now: dt.datetime
) -> RateLimitState:
    """Ventana deslizante contando sobre `responses_by_respondent`.

    Sin Redis ni contador en memoria: además de ahorrar infraestructura, evita que el límite se
    reinicie en cada despliegue (`docs/12-api.md` §4). Con el índice es un recorrido de unas
    pocas decenas de filas.

    El límite por hash de IP que menciona §4 **no está implementado**: `responses` no guarda
    ninguna columna derivada de la IP, y agregarla contradiría RNF-05. Queda el límite por
    respondedor, que es el que describe el párrafo de implementación del mismo documento.
    """
    minute_ago = now - dt.timedelta(minutes=1)
    day_ago = now - dt.timedelta(days=1)

    in_minute = await _count_since(session, respondent, minute_ago)
    if in_minute >= PER_MINUTE:
        oldest = (
            await session.execute(
                sa.select(sa.func.min(Response.created_at)).where(
                    Response.respondent_id == respondent.respondent_id,
                    Response.created_at > minute_ago,
                )
            )
        ).scalar_one()
        retry_after = max(1, int((oldest + dt.timedelta(minutes=1) - now).total_seconds()))
        raise RateLimitError(retry_after)

    in_day = await _count_since(session, respondent, day_ago)
    if in_day >= PER_DAY:
        raise RateLimitError(int(dt.timedelta(days=1).total_seconds()))

    return RateLimitState(
        limit=PER_MINUTE,
        remaining=PER_MINUTE - in_minute - 1,
        reset=int((now + dt.timedelta(minutes=1)).timestamp()),
    )


async def record(
    session: AsyncSession,
    respondent: Respondent,
    question: Question,
    answer: dict[str, Any],
    response_time_ms: int,
    now: dt.datetime,
) -> Response:
    """Inserta la respuesta y actualiza los contadores, en una sola transacción.

    `type` y `patch_id` se copian de la pregunta: son redundantes a propósito —permiten expresar
    la validación del `answer` como restricción de tabla y que el pipeline recorra por parche y
    tipo sin tocar `questions`— y la consistencia la garantiza este INSERT
    (`docs/11-modelo-de-datos.md` §3.9).
    """
    response = Response(
        respondent_id=respondent.respondent_id,
        question_id=question.question_id,
        type=question.type,
        patch_id=question.patch_id,
        answer=answer,
        response_time_ms=response_time_ms,
    )
    session.add(response)
    await streaks.apply(session, respondent, now)
    await session.commit()
    await session.refresh(response)
    return response


async def build_feedback(
    session: AsyncSession, question: Question, answer: dict[str, Any]
) -> Feedback | None:
    """El consenso de la comunidad, o `None` si todavía no hay soporte suficiente.

    Sale del campo denormalizado `questions.answer_counts`, que refresca cada 15 minutos el job
    `refresh_question_stats`: calcularlo en vivo sería un GROUP BY en el camino crítico. Puede
    estar levemente desactualizado, lo cual es irrelevante para un mensaje motivacional.

    Con menos de `sampler.consensus_threshold` respuestas se devuelve `None` y la interfaz dice
    *"you're one of the first to answer this"*, para no anclar a los primeros sobre ruido
    (ADR-012, RF-114). **En la semana 2 ese job todavía no existe**, así que `answer_counts` está
    vacío y esta función devuelve `None` siempre: es el comportamiento correcto para un piloto
    que arranca sin datos.
    """
    threshold = await app_settings.get(session, "sampler.consensus_threshold", 20)
    counts: dict[str, int] = question.answer_counts or {}
    sample_size = sum(counts.values())
    if sample_size < threshold:
        return None

    consensus = {key: value / sample_size for key, value in counts.items()}
    majority = max(counts, key=lambda k: counts[k])
    return Feedback(
        consensus=consensus,
        agreed_with_majority=answer.get("choice") == majority,
        sample_size=sample_size,
    )


def build_progress(respondent: Respondent, agreement_rate: float) -> Progress:
    return Progress(
        answers_count=respondent.answers_count,
        current_streak=respondent.current_streak,
        best_streak=respondent.best_streak,
        current_day_streak=respondent.current_day_streak,
        best_day_streak=respondent.best_day_streak,
        agreement_rate=agreement_rate,
    )
