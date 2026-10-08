"""Honeypots: cómo se evalúan, cuál se sirve y cuándo se retiran (`docs/22-calidad-de-datos.md` §3).

Una honeypot no mide la verdad: mide si la persona está leyendo y sabe de qué se le habla. Por eso
sale de un hecho del kit (ADR-013) y por eso el sistema vigila sus propias honeypots y retira la
que falla demasiada gente, que casi siempre es una honeypot mal escrita.

`is_honeypot` y `expected_answer` **nunca salen de la base** (RF-202, CA-103): nada de este módulo
llega a un schema de respuesta.
"""

from __future__ import annotations

import random
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Question, QuestionType, Respondent, Response
from app.services import app_settings, trust
from app.services.answers import UNKNOWN_CHOICE
from app.services.questions import Space

#: Las seis dimensiones que un hecho del kit resuelve sin discusión (ADR-013). `scaling` y `pick`
#: no tienen honeypots, y no es una omisión.
ELIGIBLE_DIMENSIONS: Final = frozenset({"mobility", "cc", "poke", "waveclear", "engage", "peel"})

#: El tipo de todas las honeypots (§3.2): es el único con una respuesta que el kit decide.
HONEYPOT_TYPE: Final = QuestionType.PAIRWISE_DIMENSION


def evaluate(answer: dict[str, Any], expected: dict[str, Any] | None) -> bool | None:
    """Si la respuesta coincide con la esperada, o `None` si fue `unknown` (§3.5).

    `unknown` es neutro a propósito: penalizar el «no estoy seguro» empuja a adivinar, y una
    adivinanza entra al crudo como si fuera una opinión. La comparación es la misma igualdad de
    `jsonb` que usa el retiro, porque `expected_answer` tiene la forma de `answer`.
    """
    if answer.get("choice") == UNKNOWN_CHOICE:
        return None
    return answer == expected


async def catalog(session: AsyncSession, patch_id: int) -> list[Question]:
    """Las honeypots vigentes del parche, sobre el índice parcial `questions_honeypots`."""
    return list(
        (
            await session.execute(
                sa.select(Question)
                .where(Question.patch_id == patch_id, Question.is_honeypot)
                .order_by(Question.question_id)
            )
        ).scalars()
    )


def pick_unseen(
    honeypots: Sequence[Question],
    space: Space,
    excluded: Collection[int],
    rng: random.Random,
) -> Question | None:
    """Una honeypot al azar que el respondedor no vio y que el pool actual puede servir.

    El pool importa por la misma razón que el catálogo es sólo de tier 1: una honeypot con un
    campeón que nunca aparece en las preguntas comunes se delataría.
    """
    candidates = [
        q for q in honeypots if q.question_id not in excluded and space.admits(q)
    ]
    if not candidates:
        return None
    return rng.choice(candidates)


@dataclass(frozen=True, slots=True)
class RetireResult:
    retired: list[int]
    respondents: int


async def retire_failing(session: AsyncSession, patch_id: int) -> RetireResult:
    """Retira las honeypots del parche cuyo *pass rate* cayó bajo el umbral (§3.4). No hace commit.

    Sólo se evalúan las que tienen `quality.honeypot_min_attempts` intentos o más. No cuentan los
    `unknown` ni los respondedores marcados: si contaran, un grupo de identidades fabricadas podría
    retirar justo las honeypots que las detectan.

    Retirar es poner `is_honeypot = false`. La pregunta queda como una común más y **se recalcula
    el trust de todos los que la habían recibido**, como si nunca hubiera sido honeypot.
    """
    min_attempts = int(await app_settings.get(session, "quality.honeypot_min_attempts", 40))
    min_pass_rate = float(
        await app_settings.get(session, "quality.honeypot_min_pass_rate", 0.85)
    )
    attempts = sa.func.count()
    passed = sa.func.count().filter(Response.answer == Question.expected_answer)
    rows = await session.execute(
        sa.select(Question.question_id, attempts, passed)
        .join(Response, Response.question_id == Question.question_id)
        .join(Respondent, Respondent.respondent_id == Response.respondent_id)
        .where(
            Question.patch_id == patch_id,
            Question.is_honeypot,
            ~Respondent.is_flagged,
            Response.is_retest_of.is_(None),
            sa.func.coalesce(Response.answer["choice"].astext, "") != UNKNOWN_CHOICE,
        )
        .group_by(Question.question_id)
    )
    retired = [
        question_id
        for question_id, n_attempts, n_passed in rows.tuples()
        if n_attempts >= min_attempts and n_passed / n_attempts < min_pass_rate
    ]
    if not retired:
        return RetireResult(retired=[], respondents=0)

    await session.execute(
        sa.update(Question)
        .where(Question.question_id.in_(retired))
        .values(is_honeypot=False)
        .execution_options(synchronize_session="fetch")
    )
    affected = set(
        (
            await session.execute(
                sa.select(Response.respondent_id)
                .where(Response.question_id.in_(retired))
                .distinct()
            )
        ).scalars()
    )
    await trust.rebuild(session, affected, await trust.TrustParams.load(session))
    return RetireResult(retired=retired, respondents=len(affected))
