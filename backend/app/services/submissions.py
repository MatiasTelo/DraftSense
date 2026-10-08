"""Qué fila de `responses` cuenta como una respuesta de la persona (ADR-022).

Desde que el tipo 1 es un ranking de cinco campeones, un envío de tipo 1 inserta **diez filas**,
una por par. Para la persona es una sola respuesta: suma 1 a `answers_count`, ocupa una posición
en la sesión y cuenta una vez en el rate limit. Toda consulta que cuente o recorra las respuestas
de alguien —rate limit, regla de variedad, distancia del retest, patrones degenerados, perfil,
tabla de posiciones— tiene que mirar **envíos**, no filas.

El envío se representa con una sola de sus filas, la **cabeza**: la fila sin `ranking_id` en los
otros tipos, y la del par ancla en un ranking. El ancla nunca se ignora por repetida —si ya estaba
contestada, el envío entero es un 409—, así que todo ranking contestado tiene exactamente una
cabeza.

Si se olvida este filtro en una consulta nueva, el tipo 1 pesa diez veces más que los demás.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from app.models import Ranking, Response


def heads[T: Any](statement: T) -> T:
    """Restringe un `SELECT` que ya lee de `responses` a una fila por envío."""
    return statement.outerjoin(  # type: ignore[no-any-return]
        Ranking, Ranking.ranking_id == Response.ranking_id
    ).where(is_head())


def is_head() -> sa.ColumnElement[bool]:
    """La condición de cabeza. Necesita `rankings` unida por `ranking_id` (externa)."""
    return sa.or_(Response.ranking_id.is_(None), Response.question_id == Ranking.anchor_question_id)
