"""Las dos rachas, tal como las define `docs/23-gamificacion.md` §2.

Miden cosas distintas y por eso son dos. `current_streak` son respuestas seguidas sin una pausa
larga: es el motor intra-sesión. `current_day_streak` son días consecutivos con al menos cinco
respuestas: es el motor entre sesiones, y es el que sostiene la recolección a lo largo de las
cuatro semanas del piloto.

**Ninguna de las dos depende del contenido de la respuesta**, sólo del volumen y de la constancia.
Una racha por coincidir con el consenso rompería la independencia entre anotadores, que es un
supuesto del alfa de Krippendorff y del modelo de Bradley-Terry (§2.3).
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Respondent
from app.services import app_settings


async def apply(session: AsyncSession, respondent: Respondent, now: dt.datetime) -> None:
    """Actualiza contadores y rachas por una respuesta nueva. No hace commit.

    Corre en la misma transacción del INSERT de la respuesta y sobre columnas de la propia fila
    del respondedor, así que no cuesta una consulta extra (`docs/10-arquitectura.md` §3, paso 4).
    """
    gap_minutes = await app_settings.get(session, "gamification.streak_gap_minutes", 30)
    min_answers = await app_settings.get(session, "gamification.day_streak_min_answers", 5)
    timezone = await app_settings.get(
        session, "gamification.streak_timezone", "America/Argentina/Buenos_Aires"
    )

    # --- racha de respuestas (§2.1) ---
    previous_seen = respondent.last_seen
    if previous_seen.tzinfo is None:
        previous_seen = previous_seen.replace(tzinfo=dt.UTC)
    if now - previous_seen > dt.timedelta(minutes=gap_minutes):
        respondent.current_streak = 1
    else:
        respondent.current_streak += 1
    respondent.best_streak = max(respondent.best_streak, respondent.current_streak)

    # --- racha de días (§2.2) ---
    # El día se define en horario argentino y no en UTC: la difusión del piloto es local, y en
    # UTC alguien que responde a las 22:00 de un martes estaría sumando al miércoles.
    today = now.astimezone(ZoneInfo(timezone)).date()
    previous_date = respondent.last_active_date

    if previous_date != today:
        # Cierre del día anterior. La racha sobrevive sólo si ese día fue ayer Y llegó al umbral;
        # `answers_today` todavía tiene su conteo, que es la única forma de saberlo sin una
        # columna extra ni consultar `responses`.
        #
        # El pseudocódigo de §2.2 hace esta comparación más abajo, al cruzar el umbral, contra
        # `last_active_date` — pero para entonces ya vale hoy, así que la condición nunca se
        # cumple y la racha se reiniciaría en 1 todos los días. Acá se evalúa en el único momento
        # en que el dato del día anterior todavía existe.
        sustained = (
            previous_date is not None
            and previous_date == today - dt.timedelta(days=1)
            and respondent.answers_today >= min_answers
        )
        if not sustained:
            respondent.current_day_streak = 0
        respondent.answers_today = 0
        respondent.last_active_date = today

    respondent.answers_today += 1

    # Se suma al CRUZAR el umbral, no cada vez que se lo supera: 20 respuestas en un día suman
    # uno a la racha, no dieciséis (CA-311).
    if respondent.answers_today == min_answers:
        respondent.current_day_streak += 1
        respondent.best_day_streak = max(
            respondent.best_day_streak, respondent.current_day_streak
        )

    respondent.answers_count += 1
    respondent.last_seen = now
