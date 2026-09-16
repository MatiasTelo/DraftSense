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

Cubre los tres tipos que existen desde la semana 4: el 1, el 2 y la variante 1v1 del 3. Cada uno
normaliza la entropía a su manera (`docs/21-sampler.md` §3.2). Los tipos 4 y 5 entran en la
semana 8; agregar uno es sumarlo a `REFRESHED_TYPES` y darle su rama en `entropy_for`.

Dos cosas que el job también hará y que **deliberadamente todavía no hace**, porque dependen de
módulos de la semana 5: `coverage_deficit` (`docs/21-sampler.md` §3.3), que sólo alimenta a la
función de prioridad, y el retiro de las honeypots cuyo *pass rate* cayó por debajo del umbral
(`docs/22-calidad-de-datos.md`), que necesita que existan honeypots.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Patch, Question, QuestionType, Response

REFRESHED_TYPES: Final = (
    QuestionType.PAIRWISE_DIMENSION,
    QuestionType.PEAK_TIMING,
    QuestionType.LANE_MATCHUP,
)

#: El rango intercuartil que satura la entropía del tipo 2 (`docs/21-sampler.md` §3.2): con 12
#: minutos entre cuartiles la comunidad está tan dividida como puede estarlo para el sampler.
PEAK_IQR_SCALE: Final = 12

#: El colapso de la escala del tipo 3 a tres resultados. *Wins hard* y *wins slightly* dicen lo
#: mismo sobre quién gana, y la entropía mide desacuerdo sobre eso, no sobre el margen.
LANE_OUTCOME: Final[dict[str, str]] = {
    "a_strong": "a",
    "a_slight": "a",
    "even": "even",
    "b_slight": "b",
    "b_strong": "b",
}


@dataclass(slots=True)
class RefreshResult:
    """Lo que el comando de CLI imprime al terminar."""

    patch: str | None
    questions: int
    responses: int


def _as_entropy(value: float) -> Decimal:
    """Recorta a `[0, 1]` y fija cuatro decimales, que es lo que admite la columna.

    El máximo teórico de cada fórmula es exactamente 1, pero el redondeo del flotante puede
    devolver 1.0000000000000002 y `questions_entropy_range` rechaza cualquier cosa fuera de
    `[0, 1]`. Sin este recorte el job falla contra la base en la mitad de los casos.
    """
    return Decimal(f"{min(1.0, max(0.0, value)):.4f}")


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
    return _as_entropy(-p * math.log2(p) - (1 - p) * math.log2(1 - p))


def lane_entropy(counts: Mapping[str, int]) -> Decimal | None:
    """Entropía de Shannon sobre {gana A, parejo, gana B}, dividida por `log₂ 3`."""
    outcomes = {"a": 0, "even": 0, "b": 0}
    for key, count in counts.items():
        outcomes[LANE_OUTCOME[key]] += count
    total = sum(outcomes.values())
    if total == 0:
        return None
    shannon = -sum((n / total) * math.log2(n / total) for n in outcomes.values() if n)
    return _as_entropy(shannon / math.log2(3))


def peak_minutes(counts: Mapping[str, int]) -> list[int]:
    """Expande el histograma del tipo 2 a la lista ordenada de minutos.

    Las claves son texto —así las guarda el `jsonb`— y se convierten a enteros antes de operar:
    como texto, "10" es menor que "9" y la mediana de "9", "10" y "30" daría "30". `int()` falla
    ruidosamente si alguien insertó un minuto con decimales saltando la API, que es lo que
    corresponde ante un problema de integridad del crudo.
    """
    minutes: list[int] = []
    for key in sorted(counts, key=int):
        minutes.extend([int(key)] * counts[key])
    return minutes


def peak_entropy(counts: Mapping[str, int]) -> Decimal | None:
    """`min(1, IQR / 12)` sobre los minutos declarados (`docs/21-sampler.md` §3.2).

    Los cuartiles son los de interpolación lineal (`method="inclusive"`, el tipo 7 de Hyndman y
    Fan que usa numpy por defecto). Con menos de dos respuestas no hay rango que medir y la
    entropía queda en `None`; la guarda explícita además iguala el comportamiento entre Python 3.12,
    donde `quantiles` falla con un solo dato, y las versiones posteriores, donde no.
    """
    minutes = peak_minutes(counts)
    if len(minutes) < 2:
        return None
    q1, _, q3 = statistics.quantiles(minutes, n=4, method="inclusive")
    return _as_entropy(min(1.0, (q3 - q1) / PEAK_IQR_SCALE))


def peak_median(counts: Mapping[str, int]) -> int | None:
    """La mediana sin ponderar de los minutos, entera, con el medio hacia arriba.

    Es la que muestra el feedback (`docs/12-api.md` §2.4), no la del CSV: esa la pondera por
    confianza el pipeline de agregación. No se usa `round()` porque redondea al par —26,5 daría 26
    y 25,5 también—; el contrato pide que 26,5 se informe como 27.
    """
    minutes = peak_minutes(counts)
    if not minutes:
        return None
    return math.floor(statistics.median(minutes) + 0.5)


def entropy_for(question_type: QuestionType, counts: Mapping[str, int]) -> Decimal | None:
    match question_type:
        case QuestionType.PAIRWISE_DIMENSION:
            return binary_entropy(counts.get("a", 0), counts.get("b", 0))
        case QuestionType.PEAK_TIMING:
            return peak_entropy(counts)
        case QuestionType.LANE_MATCHUP:
            return lane_entropy(counts)
        case _:
            return None


async def _questions(session: AsyncSession, patch_id: int) -> list[tuple[int, QuestionType]]:
    rows = await session.execute(
        sa.select(Question.question_id, Question.type).where(
            Question.patch_id == patch_id,
            Question.type.in_(REFRESHED_TYPES),
        )
    )
    return [(question_id, question_type) for question_id, question_type in rows.all()]


async def _counts_by_answer(session: AsyncSession, patch_id: int) -> dict[int, dict[str, int]]:
    """Un `GROUP BY` por pregunta y respuesta, sobre `responses_by_question`.

    La clave agrupada es el minuto en el tipo 2 y la opción elegida en los demás. Es la consulta
    cara del sistema, y por eso vive acá y no en el camino crítico.
    """
    key = sa.case(
        (Question.type == QuestionType.PEAK_TIMING, Response.answer["minute"].astext),
        else_=Response.answer["choice"].astext,
    )
    rows = (
        await session.execute(
            sa.select(Response.question_id, key, sa.func.count())
            .join(Question, Question.question_id == Response.question_id)
            .where(
                Question.patch_id == patch_id,
                Question.type.in_(REFRESHED_TYPES),
            )
            .group_by(Response.question_id, key)
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
    questions = await _questions(session, patch.patch_id)
    counts = await _counts_by_answer(session, patch.patch_id)

    payload: list[dict[str, Any]] = []
    for question_id, question_type in questions:
        row = counts.get(question_id, {})
        payload.append(
            {
                "question_id": question_id,
                "answer_counts": row,
                "exposure_count": sum(row.values()),
                "entropy": entropy_for(question_type, row),
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
