"""La tabla de posiciones.

Ordenada por cantidad de respuestas y **filtrada dos veces**: quedan fuera los marcados y los que
están por debajo de `export.min_trust` (ADR-014). Sin el segundo filtro, con el límite de 1 500
respuestas diarias alguien que conteste basura a toda velocidad lidera la tabla: sus respuestas se
descartan en el export, pero públicamente gana. Estaríamos premiando en la pantalla principal
exactamente el comportamiento que el módulo de calidad existe para descartar.

Eso **no expone el trust score**. No se publica el valor ni el orden por trust, y el orden sigue
siendo por cantidad de respuestas, que el usuario ya conoce de su propio perfil. Lo único
observable es un bit —alguien no aparece—, y no permite saber si está en 0.29 o en 0.05
(`docs/23-gamificacion.md` §5.2).
"""

from __future__ import annotations

import datetime as dt
import time
import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Respondent, Response
from app.schemas.profile import LeaderboardEntry, LeaderboardOut
from app.services import app_settings

WINDOWS = ("day", "week", "all")

#: (window) -> (momento del cálculo, filas). Una tabla que se actualiza cada minuto es
#: indistinguible de una en vivo para quien la mira, y saca la consulta del camino de cada
#: petición (`docs/23-gamificacion.md` §5.3).
_cache: dict[str, tuple[float, dt.datetime, list[tuple[uuid.UUID, str | None, int]]]] = {}


def reset_cache() -> None:
    _cache.clear()


def window_start(window: str, now: dt.datetime) -> dt.datetime | None:
    if window == "day":
        return now - dt.timedelta(days=1)
    if window == "week":
        return now - dt.timedelta(days=7)
    return None


async def _query(
    session: AsyncSession, window: str, now: dt.datetime, size: int, min_trust: Decimal
) -> list[tuple[uuid.UUID, str | None, int]]:
    eligible = (~Respondent.is_flagged, Respondent.trust_score >= min_trust)
    start = window_start(window, now)
    if start is None:
        # `answers_count` es un contador total y sólo sirve para la ventana completa.
        statement = (
            sa.select(Respondent.respondent_id, Respondent.alias, Respondent.answers_count)
            .where(*eligible)
            .order_by(Respondent.answers_count.desc(), Respondent.respondent_id)
            .limit(size)
        )
    else:
        total = sa.func.count(Response.response_id).label("n")
        statement = (
            sa.select(Respondent.respondent_id, Respondent.alias, total)
            .join(Response, Response.respondent_id == Respondent.respondent_id)
            .where(*eligible, Response.created_at > start)
            .group_by(Respondent.respondent_id, Respondent.alias)
            .order_by(total.desc(), Respondent.respondent_id)
            .limit(size)
        )
    return [(row[0], row[1], row[2]) for row in (await session.execute(statement)).all()]


async def build(
    session: AsyncSession, window: str, viewer: Respondent, now: dt.datetime
) -> LeaderboardOut:
    size = await app_settings.get(session, "gamification.leaderboard_size", 50)
    ttl = await app_settings.get(session, "gamification.leaderboard_cache_seconds", 60)
    min_trust = Decimal(str(await app_settings.get(session, "export.min_trust", 0.30)))

    cached = _cache.get(window)
    if cached is None or time.monotonic() - cached[0] > ttl:
        rows = await _query(session, window, now, size, min_trust)
        cached = (time.monotonic(), now, rows)
        _cache[window] = cached

    _, generated_at, rows = cached
    return LeaderboardOut(
        window=window,
        generated_at=generated_at,
        entries=[
            LeaderboardEntry(
                rank=index,
                alias=alias,
                answers_count=count,
                is_you=respondent_id == viewer.respondent_id,
            )
            for index, (respondent_id, alias, count) in enumerate(rows, start=1)
        ],
    )
