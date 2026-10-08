"""Qué respuestas entrarían hoy a la agregación: los filtros de `docs/25-agregacion.md` §1.

Dos cosas del backend necesitan anticipar lo que va a ver el pipeline de la semana 9 sin correrlo:
las aristas del grafo de conectividad (ADR-021) y los conteos del déficit de cobertura
(`docs/21-sampler.md` §3.3). Las dos usan estos filtros, y los usan de acá para que no se separen.

La ventana de parches no está: los dos consumidores miran sólo el parche vigente.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Question, Respondent, Response
from app.services import app_settings

#: La misma clave que el filtro de exportación y la tabla de posiciones (ADR-014), no una copia.
MIN_TRUST_KEY: Final = "export.min_trust"


async def min_trust(session: AsyncSession) -> Decimal:
    return Decimal(str(await app_settings.get(session, MIN_TRUST_KEY, 0.30)))


def source() -> sa.Join:
    """`responses` unida con su pregunta y su respondedor, que es donde viven los filtros.

    Es un `FROM` y no una función sobre el `Select` porque el tipo genérico de `Select` cambió
    entre SQLAlchemy 2.0 y 2.1, y una firma genérica no tipa en las dos.
    """
    return sa.join(Response, Question, Question.question_id == Response.question_id).join(
        Respondent, Respondent.respondent_id == Response.respondent_id
    )


def conditions(threshold: Decimal) -> list[sa.ColumnElement[bool]]:
    """Los cuatro filtros de 25 §1 que no son la ventana."""
    return [
        Response.is_retest_of.is_(None),
        ~Question.is_honeypot,
        ~Respondent.is_flagged,
        Respondent.trust_score >= threshold,
    ]
