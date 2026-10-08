"""El trust score: la fórmula de `docs/22-calidad-de-datos.md` §7.1 y sus recálculos (§7.2).

`trust_score` es una **caché**: se puede reconstruir entero desde `responses`, el catálogo de
honeypots y los retests. Este módulo tiene la fórmula y dos formas de recalcularla:

- `refresh`, sobre los contadores que ya tiene la fila. Es aritmética pura y es lo que usa
  `POST /responses` cuando la pregunta era honeypot o retest, dentro de la misma transacción.
- `rebuild`, que vuelve a contar honeypots y retests desde el crudo. Lo usa el retiro automático
  de una honeypot (§3.4), que exige recalcular «como si nunca hubiera existido».

La tercera forma —la diferida— es `degenerate.detect`, que recuenta los patrones degenerados. La
verificación desde cero de las seis señales está en `trust_check`.

**El valor nunca sale de la API** (RF-207). Nada de acá lo devuelve a un router.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Question, Respondent, Response
from app.services import app_settings, retests

#: La media a priori del suavizado: el `0.5` de `2 · 0.5` en §7.1. Con ella, un respondedor sin
#: honeypots ni retests da exactamente `h = r = 0.5` y el trust coincide con el DEFAULT de la
#: columna. Cambiarla rompe esa coincidencia.
PRIOR: Final = 0.5

#: El piso del denominador de `d` (§7.1). Sin él, tres respuestas apuradas entre las primeras cinco
#: darían `d = 1` y castigarían a alguien que recién empieza.
DEGENERATE_FLOOR: Final = 20

#: La fracción del volumen que satura `d`: con respuestas degeneradas en el 15 % de las
#: respuestas, el descuento es completo.
DEGENERATE_SHARE: Final = 0.15

#: Una racha de *straightlining* pesa como dos respuestas apuradas (§7.1).
STRAIGHTLINE_WEIGHT: Final = 2

DEFAULT_WEIGHTS: Final = {"honeypot": 0.60, "retest": 0.40, "degenerate": 0.50}
DEFAULT_SMOOTHING: Final = 2

_THOUSANDTH = Decimal("0.001")


@dataclass(frozen=True, slots=True)
class TrustParams:
    """Los parámetros de la fórmula, leídos de `app_settings` (§8)."""

    honeypot: float
    retest: float
    degenerate: float
    smoothing: float

    @classmethod
    def from_settings(cls, weights: Mapping[str, Any], smoothing: float) -> TrustParams:
        return cls(
            honeypot=float(weights["honeypot"]),
            retest=float(weights["retest"]),
            degenerate=float(weights["degenerate"]),
            smoothing=float(smoothing),
        )

    @classmethod
    async def load(cls, session: AsyncSession) -> TrustParams:
        weights = await app_settings.get(session, "quality.trust_weights", DEFAULT_WEIGHTS)
        smoothing = await app_settings.get(session, "quality.trust_smoothing", DEFAULT_SMOOTHING)
        return cls.from_settings(weights, smoothing)


DEFAULT_PARAMS: Final = TrustParams.from_settings(DEFAULT_WEIGHTS, DEFAULT_SMOOTHING)


@dataclass(frozen=True, slots=True)
class Counters:
    """Las seis señales del respondedor, más el volumen que normaliza a `d`."""

    honeypot_attempts: int = 0
    honeypot_passed: int = 0
    retest_pairs: int = 0
    retest_consistent: int = 0
    fast_answers: int = 0
    straightline_runs: int = 0
    answers_count: int = 0

    @classmethod
    def of(cls, respondent: Respondent) -> Counters:
        return cls(
            honeypot_attempts=respondent.honeypot_attempts,
            honeypot_passed=respondent.honeypot_passed,
            retest_pairs=respondent.retest_pairs,
            retest_consistent=respondent.retest_consistent,
            fast_answers=respondent.fast_answers,
            straightline_runs=respondent.straightline_runs,
            answers_count=respondent.answers_count,
        )


def compute(counters: Counters, params: TrustParams = DEFAULT_PARAMS) -> Decimal:
    """La fórmula de §7.1, redondeada a los tres decimales de `numeric(4,3)`.

    El redondeo es explícito y hacia arriba en el medio: Postgres redondearía igual al guardar,
    pero el valor que queda en el objeto tiene que ser el mismo que queda en la fila, o una
    comparación posterior contra la base daría una divergencia falsa.
    """
    s = params.smoothing
    h = (counters.honeypot_passed + s * PRIOR) / (counters.honeypot_attempts + s)
    r = (counters.retest_consistent + s * PRIOR) / (counters.retest_pairs + s)
    degenerate_events = counters.fast_answers + STRAIGHTLINE_WEIGHT * counters.straightline_runs
    d = min(
        1.0,
        degenerate_events / max(DEGENERATE_FLOOR, DEGENERATE_SHARE * counters.answers_count),
    )
    value = (params.honeypot * h + params.retest * r) * (1 - params.degenerate * d)
    clamped = min(1.0, max(0.0, value))
    return Decimal(str(clamped)).quantize(_THOUSANDTH, rounding=ROUND_HALF_UP)


def refresh(respondent: Respondent, params: TrustParams) -> None:
    """Recalcula el trust con los contadores que ya tiene la fila. No hace commit."""
    respondent.trust_score = compute(Counters.of(respondent), params)


async def honeypot_counts(
    session: AsyncSession, respondent_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    """Intentos y aciertos contra las preguntas que **hoy** son honeypot.

    Una honeypot retirada ya no cuenta, que es exactamente lo que pide §3.4. `unknown` no es un
    intento (§3.5).
    """
    rows = await session.execute(
        sa.select(Response.respondent_id, Response.answer, Question.expected_answer)
        .join(Question, Question.question_id == Response.question_id)
        .where(
            Question.is_honeypot,
            Response.respondent_id.in_(respondent_ids),
            Response.is_retest_of.is_(None),
        )
    )
    counts: dict[uuid.UUID, tuple[int, int]] = {}
    for respondent_id, answer, expected in rows.all():
        if answer.get("choice") == retests.UNKNOWN:
            continue
        attempts, passed = counts.get(respondent_id, (0, 0))
        counts[respondent_id] = (attempts + 1, passed + int(answer == expected))
    return counts


async def retest_counts(
    session: AsyncSession, respondent_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    """Pares y pares consistentes, con el criterio por tipo de §4."""
    original = aliased(Response)
    rows = await session.execute(
        sa.select(Response.respondent_id, Response.type, original.answer, Response.answer)
        .join(original, original.response_id == Response.is_retest_of)
        .where(Response.respondent_id.in_(respondent_ids))
    )
    counts: dict[uuid.UUID, tuple[int, int]] = {}
    for respondent_id, question_type, first, repeat in rows.all():
        consistent = retests.is_consistent(question_type, first, repeat)
        if consistent is None:
            continue
        pairs, hits = counts.get(respondent_id, (0, 0))
        counts[respondent_id] = (pairs + 1, hits + int(consistent))
    return counts


async def _respondents(
    session: AsyncSession, respondent_ids: Collection[uuid.UUID]
) -> list[Respondent]:
    if not respondent_ids:
        return []
    return list(
        (
            await session.execute(
                sa.select(Respondent).where(Respondent.respondent_id.in_(respondent_ids))
            )
        ).scalars()
    )


async def rebuild(
    session: AsyncSession, respondent_ids: Collection[uuid.UUID], params: TrustParams
) -> int:
    """Vuelve a contar honeypots y retests desde el crudo y recalcula el trust. No hace commit.

    Los contadores de patrones degenerados no se tocan: los mantiene `detect_degenerate_patterns`,
    que es el único que los recalcula (§7.2). Devuelve cuántos trust cambiaron.
    """
    ids = set(respondent_ids)
    if not ids:
        return 0
    honeypots = await honeypot_counts(session, ids)
    pairs = await retest_counts(session, ids)
    changed = 0
    for respondent in await _respondents(session, ids):
        attempts, passed = honeypots.get(respondent.respondent_id, (0, 0))
        retest_pairs, consistent = pairs.get(respondent.respondent_id, (0, 0))
        respondent.honeypot_attempts = attempts
        respondent.honeypot_passed = passed
        respondent.retest_pairs = retest_pairs
        respondent.retest_consistent = consistent
        before = respondent.trust_score
        refresh(respondent, params)
        changed += int(respondent.trust_score != before)
    return changed
