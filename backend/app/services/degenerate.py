"""El job `detect_degenerate_patterns` (`docs/22-calidad-de-datos.md` §5).

Detecta respuestas apuradas y rachas de *straightlining*, y recalcula el trust con eso. No marca a
nadie: las dos señales entran a la fórmula como un descuento proporcional al volumen, porque una
respuesta rápida suelta no significa nada (§5.1).

**Recalcula desde cero** (nota del 16/09 en §5): para cada respondedor con actividad en la ventana,
vuelve a contar sobre toda su historia. Sumar sólo lo nuevo exigiría guardar hasta dónde llegó la
corrida anterior; sin esa marca, correrlo dos veces el mismo día duplicaría los contadores.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuestionType, Respondent, Response
from app.services import app_settings, trust
from app.services.answers import UNKNOWN_CHOICE

#: Los tipos con posición en pantalla. El tipo 2 es un slider; los 4 y 5 entran en la semana 8.
STRAIGHTLINE_TYPES: Final = (QuestionType.PAIRWISE_DIMENSION, QuestionType.LANE_MATCHUP)


@dataclass(frozen=True, slots=True)
class HistoryRow:
    type: QuestionType
    answer: dict[str, Any]
    response_time_ms: int


def straightline_runs(keys: Iterable[str | None], run_length: int) -> int:
    """Cuántos tramos de `run_length` o más respuestas seguidas en la misma posición hay.

    `keys` es la subsecuencia de **un** tipo, en orden. La posición es la clave de la opción: el
    servidor manda siempre `a` a la izquierda y la escala del tipo 3 en el mismo orden, y el cliente
    la dibuja así. `unknown` corta la racha y no forma una propia: contarlo castigaría la respuesta
    honesta de quien no conoce a esos campeones (§5.2, nota del 16/09). Un tramo largo es una sola
    racha.
    """
    runs = 0
    current: str | None = None
    length = 0
    for key in keys:
        if key is None or key == UNKNOWN_CHOICE:
            current, length = None, 0
            continue
        if key == current:
            length += 1
        else:
            current, length = key, 1
        if length == run_length:
            runs += 1
    return runs


def count(rows: Sequence[HistoryRow], fast_answer_ms: int, run_length: int) -> tuple[int, int]:
    """`(fast_answers, straightline_runs)` sobre la historia completa de un respondedor.

    Entran todas las respuestas, también las de honeypots y retests: la señal mide cómo se toca la
    pantalla, no qué pregunta era.
    """
    fast = sum(1 for row in rows if row.response_time_ms < fast_answer_ms)
    runs = sum(
        straightline_runs(
            (row.answer.get("choice") for row in rows if row.type is question_type), run_length
        )
        for question_type in STRAIGHTLINE_TYPES
    )
    return fast, runs


async def history(
    session: AsyncSession, respondent_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, list[HistoryRow]]:
    """Las respuestas de cada respondedor, en el orden en que las dio."""
    if not respondent_ids:
        return {}
    rows = await session.execute(
        sa.select(
            Response.respondent_id, Response.type, Response.answer, Response.response_time_ms
        )
        .where(Response.respondent_id.in_(list(respondent_ids)))
        .order_by(Response.respondent_id, Response.created_at, Response.response_id)
    )
    grouped: dict[uuid.UUID, list[HistoryRow]] = {}
    for respondent_id, question_type, answer, elapsed in rows.tuples():
        grouped.setdefault(respondent_id, []).append(
            HistoryRow(type=QuestionType(question_type), answer=answer, response_time_ms=elapsed)
        )
    return grouped


@dataclass(frozen=True, slots=True)
class DetectResult:
    respondents: int
    changed: int


async def detect(
    session: AsyncSession, now: dt.datetime | None = None, since_hours: int = 24
) -> DetectResult:
    """Recuenta las dos señales de los respondedores activos y recalcula su trust. Hace commit."""
    moment = now or dt.datetime.now(dt.UTC)
    active = set(
        (
            await session.execute(
                sa.select(Response.respondent_id)
                .where(Response.created_at > moment - dt.timedelta(hours=since_hours))
                .distinct()
            )
        ).scalars()
    )
    if not active:
        return DetectResult(respondents=0, changed=0)

    fast_ms = int(await app_settings.get(session, "quality.fast_answer_ms", 800))
    run_length = int(await app_settings.get(session, "quality.straightline_run", 8))
    params = await trust.TrustParams.load(session)
    rows_by_respondent = await history(session, active)
    respondents = (
        await session.execute(sa.select(Respondent).where(Respondent.respondent_id.in_(active)))
    ).scalars()

    changed = 0
    for respondent in respondents:
        rows = rows_by_respondent.get(respondent.respondent_id, [])
        fast, runs = count(rows, fast_ms, run_length)
        if (fast, runs) != (respondent.fast_answers, respondent.straightline_runs):
            changed += 1
        respondent.fast_answers = fast
        respondent.straightline_runs = runs
        trust.refresh(respondent, params)
    await session.commit()
    return DetectResult(respondents=len(active), changed=changed)
