"""La verificación del trust score (`docs/22-calidad-de-datos.md` §7.2).

`trust_score` y sus seis contadores son cachés que mantienen tres caminos distintos: el `POST`, el
retiro de honeypots y el job de patrones degenerados. Un error en cualquiera de ellos no tira una
excepción: deja un contador desviado y un peso equivocado en la agregación. Esta verificación
recalcula todo desde `responses` y compara, **sin escribir nada**.

Una divergencia en `fast_answers` o `straightline_runs` puede ser sólo que el job diario todavía no
corrió sobre las respuestas de hoy. Una en honeypots o retests es un error.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass, replace
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Respondent
from app.services import app_settings, degenerate, trust


async def recount(
    session: AsyncSession,
    respondent_ids: Collection[uuid.UUID],
    fast_answer_ms: int,
    run_length: int,
) -> dict[uuid.UUID, trust.Counters]:
    """Las seis señales de cada respondedor, contadas desde `responses`."""
    ids = set(respondent_ids)
    if not ids:
        return {}
    honeypots = await trust.honeypot_counts(session, ids)
    pairs = await trust.retest_counts(session, ids)
    history = await degenerate.history(session, ids)
    result: dict[uuid.UUID, trust.Counters] = {}
    for respondent_id in ids:
        rows = history.get(respondent_id, [])
        fast, runs = degenerate.count(rows, fast_answer_ms, run_length)
        attempts, passed = honeypots.get(respondent_id, (0, 0))
        retest_pairs, consistent = pairs.get(respondent_id, (0, 0))
        result[respondent_id] = trust.Counters(
            honeypot_attempts=attempts,
            honeypot_passed=passed,
            retest_pairs=retest_pairs,
            retest_consistent=consistent,
            fast_answers=fast,
            straightline_runs=runs,
            answers_count=len(rows),
        )
    return result


@dataclass(frozen=True, slots=True)
class Divergence:
    """Un respondedor cuyo trust o contadores guardados no coinciden con los del crudo."""

    respondent_id: uuid.UUID
    stored: Decimal
    expected: Decimal
    stored_counters: trust.Counters
    expected_counters: trust.Counters


async def verify(session: AsyncSession) -> tuple[int, list[Divergence]]:
    """Recalcula el trust de todos los respondedores y devuelve `(revisados, divergencias)`.

    `answers_count` se toma de la fila y no del recuento: lo mantiene la gamificación, y su desvío
    no es un problema de calidad.
    """
    params = await trust.TrustParams.load(session)
    fast_ms = int(await app_settings.get(session, "quality.fast_answer_ms", 800))
    run_length = int(await app_settings.get(session, "quality.straightline_run", 8))
    respondents = list((await session.execute(sa.select(Respondent))).scalars())
    expected = await recount(session, [r.respondent_id for r in respondents], fast_ms, run_length)

    divergences: list[Divergence] = []
    for respondent in respondents:
        stored_counters = trust.Counters.of(respondent)
        counted = replace(
            expected[respondent.respondent_id], answers_count=respondent.answers_count
        )
        value = trust.compute(counted, params)
        if value != respondent.trust_score or counted != stored_counters:
            divergences.append(
                Divergence(
                    respondent_id=respondent.respondent_id,
                    stored=respondent.trust_score,
                    expected=value,
                    stored_counters=stored_counters,
                    expected_counters=counted,
                )
            )
    return len(respondents), divergences
