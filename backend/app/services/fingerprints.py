"""El job `flag_duplicate_fingerprints` (`docs/22-calidad-de-datos.md` §6).

Detecta la fabricación de identidades: borrar las cookies da un respondedor nuevo, y sin login no
hay otra forma de notarlo que la huella. Se cuenta por **creación** (`first_seen`), no por
actividad, para no marcar una PC compartida donde varias personas usan identidades viejas.

Se marcan **todas** las identidades de la huella, incluida la primera: no hay forma de saber cuál
era la original (CA-306). Ninguna respuesta se borra; las de un marcado sólo dejan de entrar a la
agregación y a la tabla de posiciones.

El falso positivo de una sala con equipos clonados es conocido y está aceptado (§6.3).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Respondent
from app.services import app_settings

WINDOW: Final = dt.timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class FlagResult:
    fingerprints: int
    flagged: int


async def flag_duplicates(session: AsyncSession, now: dt.datetime | None = None) -> FlagResult:
    """Marca las identidades de toda huella que creó más del umbral en 24 h. Hace commit."""
    moment = now or dt.datetime.now(dt.UTC)
    limit = int(await app_settings.get(session, "quality.fingerprint_max_identities", 5))
    crowded = (
        sa.select(Respondent.fingerprint_hash)
        .where(Respondent.first_seen > moment - WINDOW)
        .group_by(Respondent.fingerprint_hash)
        .having(sa.func.count() > limit)
    )
    fingerprints = len((await session.execute(crowded)).all())
    flagged = (
        await session.execute(
            sa.update(Respondent)
            .where(Respondent.fingerprint_hash.in_(crowded), ~Respondent.is_flagged)
            .values(is_flagged=True)
            .returning(Respondent.respondent_id)
            .execution_options(synchronize_session="fetch")
        )
    ).all()
    await session.commit()
    return FlagResult(fingerprints=fingerprints, flagged=len(flagged))
