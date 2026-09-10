"""El perfil del respondedor: cobertura, tasa de acuerdo y percentil.

`docs/23-gamificacion.md` §3 define los tres y **no dice dónde se calculan**. Se calculan en vivo:
con el volumen del piloto —a lo sumo unos cientos de respuestas por persona— son consultas sobre
índices que ya existen, y denormalizarlos costaría dos columnas más que mantener en el camino
crítico. `tests/test_profile.py` mide la latencia para que la decisión no se sostenga sola.

Nada de lo que sale de acá permite despejar el `trust_score` (RF-207, CA-303).
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Question, QuestionType, Respondent, Response
from app.services import app_settings


async def coverage(session: AsyncSession, respondent: Respondent) -> dict[str, int]:
    """Respuestas por tipo de pregunta. Los tipos sin respuestas aparecen en cero."""
    rows = (
        await session.execute(
            sa.select(Response.type, sa.func.count())
            .where(Response.respondent_id == respondent.respondent_id)
            .group_by(Response.type)
        )
    ).all()
    counted = {question_type.value: total for question_type, total in rows}
    return {t.value: counted.get(t.value, 0) for t in QuestionType}


async def agreement_rate(session: AsyncSession, respondent: Respondent) -> float:
    """Proporción de respuestas que coincidieron con la mayoría.

    Sólo cuentan las preguntas con soporte suficiente: por debajo de
    `sampler.consensus_threshold` la "mayoría" es ruido y compararse contra ella no informa nada.

    Se resuelve trayendo `answer_counts` junto a cada respuesta y comparando en Python: la
    alternativa —despejar el argmax de un `jsonb` en SQL— es larga de escribir, difícil de leer y
    no más rápida con estos volúmenes.

    **No mide acierto.** En DraftSense no hay respuestas correctas: quien disiente de forma
    consistente es tan valioso como quien coincide, y por eso este número se muestra sin juicio y
    no alimenta ninguna recompensa (`docs/23-gamificacion.md` §2.3 y §3).
    """
    threshold = await app_settings.get(session, "sampler.consensus_threshold", 20)
    rows = (
        await session.execute(
            sa.select(Response.answer, Question.answer_counts)
            .join(Question, Question.question_id == Response.question_id)
            .where(Response.respondent_id == respondent.respondent_id)
        )
    ).all()

    eligible = 0
    agreed = 0
    for answer, counts in rows:
        choice = _choice_of(answer)
        if choice is None or not counts:
            continue
        sample_size = sum(counts.values())
        if sample_size < threshold:
            continue
        eligible += 1
        if choice == max(counts, key=lambda k: counts[k]):
            agreed += 1
    return agreed / eligible if eligible else 0.0


def _choice_of(answer: dict[str, Any]) -> str | None:
    """La opción elegida, o `None` si el tipo no se compara contra una mayoría.

    `peak_timing` responde un minuto y su consenso es una mediana, no una distribución de
    opciones: no entra en la tasa de acuerdo. `trait_multiselect` tampoco, porque la respuesta es
    un conjunto y "coincidir con la mayoría" no está definido para conjuntos.
    """
    choice = answer.get("choice")
    return choice if isinstance(choice, str) else None


async def rank_percentile(session: AsyncSession, respondent: Respondent) -> float:
    """Qué fracción de los respondedores no marcados tiene menos respuestas que éste.

    Se cuenta estrictamente por debajo, así que el que menos aportó queda en 0.0 y el que más, en
    un valor cercano a 1. Los marcados no entran ni en el numerador ni en el denominador
    (`docs/23-gamificacion.md` §3).
    """
    total = (
        await session.execute(
            sa.select(sa.func.count()).select_from(Respondent).where(~Respondent.is_flagged)
        )
    ).scalar_one()
    if not total:
        return 0.0
    below = (
        await session.execute(
            sa.select(sa.func.count())
            .select_from(Respondent)
            .where(
                ~Respondent.is_flagged,
                Respondent.answers_count < respondent.answers_count,
            )
        )
    ).scalar_one()
    return below / total
