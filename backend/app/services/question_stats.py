"""El job `refresh_question_stats`: recalcula los denormalizados de `questions`.

`questions.answer_counts`, `exposure_count` y `entropy` son cachés de cuentas sobre `responses`
(`docs/11-modelo-de-datos.md` §1.4). Existen porque sus dos consumidores —el feedback de consenso
de `POST /responses` y la función de prioridad del sampler— corren en el camino crítico, con 150 y
100 ms de presupuesto, y no pueden permitirse un `GROUP BY` sobre `responses`
(`docs/10-arquitectura.md` §4).

El job **recalcula desde cero**, no acumula: pasa por todas las preguntas del parche vigente, no
sólo por las que tienen respuestas nuevas. Es lo que hace verdadera la promesa de que lo
denormalizado se puede tirar y reconstruir, y lo que permite correrlo dos veces seguidas sin que el
resultado cambie.

**Por ahora sólo cubre el tipo 1.** Es el único que existe (`docs/20-tipos-de-pregunta.md` §8): los
otros cuatro entran en las semanas 4 y 8 y cada uno trae su propia normalización de la entropía,
tabuladas en `docs/21-sampler.md` §3.2. Agregar un tipo acá es agregar su fórmula y ampliar el
filtro de `_counts_by_choice`.

Dos cosas que el job también hará y que **deliberadamente todavía no hace**, porque dependen de
módulos de la semana 5: `coverage_deficit` (`docs/21-sampler.md` §3.3), que sólo alimenta a la
función de prioridad, y el retiro de las honeypots cuyo *pass rate* cayó por debajo del umbral
(`docs/22-calidad-de-datos.md`), que necesita que existan honeypots.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Patch, Question, QuestionType, Response


@dataclass(slots=True)
class RefreshResult:
    """Lo que el comando de CLI imprime al terminar."""

    patch: str | None
    questions: int
    responses: int


def binary_entropy(a: int, b: int) -> Decimal | None:
    """Entropía binaria sobre `{a, b}`, **ignorando `unknown`** (`docs/21-sampler.md` §3.2).

    `unknown` queda fuera a propósito y no se cuenta como una tercera opción: una pregunta con 40 %
    de `unknown` y el resto repartido mitad y mitad está tan disputada como una sin ningún
    `unknown`. Meterlo adentro confundiría «esta dimensión no aplica a este campeón» con «esta
    comparación está reñida», que son dos cosas distintas y se miden por separado — la primera sale
    como `D_unknown_rate` en el export.

    Devuelve `None` cuando no hay ninguna respuesta decisiva: la columna es nulable justamente para
    poder distinguir «entropía cero» de «todavía no se sabe».
    """
    total = a + b
    if total == 0:
        return None
    p = a / total
    if p in (0.0, 1.0):
        return Decimal("0.0000")
    value = -p * math.log2(p) - (1 - p) * math.log2(1 - p)
    # El máximo teórico es exactamente 1 en p = 0.5, pero el redondeo del flotante puede
    # devolver 1.0000000000000002 y `questions_entropy_range` rechaza cualquier cosa fuera
    # de [0,1]. Sin este recorte el job falla contra la base en la mitad de los casos.
    return Decimal(f"{min(1.0, max(0.0, value)):.4f}")


async def _question_ids(session: AsyncSession, patch_id: int) -> list[int]:
    return list(
        (
            await session.execute(
                sa.select(Question.question_id).where(
                    Question.patch_id == patch_id,
                    Question.type == QuestionType.PAIRWISE_DIMENSION,
                )
            )
        )
        .scalars()
        .all()
    )


async def _counts_by_choice(session: AsyncSession, patch_id: int) -> dict[int, dict[str, int]]:
    """Un `GROUP BY` por pregunta y opción elegida, sobre `responses_by_question`.

    Es la consulta cara del sistema, y por eso vive acá y no en el camino crítico.
    """
    choice = Response.answer["choice"].astext
    rows = (
        await session.execute(
            sa.select(Response.question_id, choice, sa.func.count())
            .join(Question, Question.question_id == Response.question_id)
            .where(
                Question.patch_id == patch_id,
                Question.type == QuestionType.PAIRWISE_DIMENSION,
            )
            .group_by(Response.question_id, choice)
        )
    ).all()

    counts: dict[int, dict[str, int]] = {}
    for question_id, value, total in rows:
        counts.setdefault(question_id, {})[value] = total
    return counts


async def refresh(session: AsyncSession, now: dt.datetime | None = None) -> RefreshResult:
    """Recalcula los denormalizados del parche vigente y hace commit.

    Sin parche vigente no hay nada que hacer: las preguntas de parches anteriores conservan sus
    valores, que es lo correcto —el crudo nunca pierde su `patch_id`, ver ADR-004— y el sampler
    sólo sirve preguntas del parche corriente.
    """
    patch = (
        await session.execute(sa.select(Patch).where(Patch.is_current))
    ).scalar_one_or_none()
    if patch is None:
        return RefreshResult(patch=None, questions=0, responses=0)

    moment = now or dt.datetime.now(dt.UTC)
    question_ids = await _question_ids(session, patch.patch_id)
    counts = await _counts_by_choice(session, patch.patch_id)

    payload: list[dict[str, Any]] = []
    for question_id in question_ids:
        row = counts.get(question_id, {})
        payload.append(
            {
                "question_id": question_id,
                "answer_counts": row,
                "exposure_count": sum(row.values()),
                "entropy": binary_entropy(row.get("a", 0), row.get("b", 0)),
                "stats_refreshed_at": moment,
            }
        )
    if payload:
        # UPDATE masivo por clave primaria: una ida a la base en vez de una por pregunta.
        await session.execute(sa.update(Question), payload)
    await session.commit()

    return RefreshResult(
        patch=patch.version,
        questions=len(payload),
        responses=sum(sum(row.values()) for row in counts.values()),
    )
