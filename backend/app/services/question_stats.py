"""El job `refresh_question_stats`: recalcula los denormalizados de `questions`.

`questions.answer_counts`, `exposure_count`, `entropy` y `coverage_deficit` son cachés de cuentas
sobre `responses` (`docs/11-modelo-de-datos.md` §1.4). Existen porque sus dos consumidores —el
feedback de consenso de `POST /responses` y la función de prioridad del sampler— corren en el
camino crítico, con 150 y 100 ms de presupuesto, y no pueden permitirse un `GROUP BY` sobre
`responses` (`docs/10-arquitectura.md` §4).

El job **recalcula desde cero**, no acumula: pasa por todas las preguntas del parche vigente, no
sólo por las que tienen respuestas nuevas. Es lo que hace verdadera la promesa de que lo
denormalizado se puede tirar y reconstruir, y lo que permite correrlo dos veces seguidas sin que el
resultado cambie.

Cubre los tres tipos que se sirven: el 1, el 2 y la variante 1v1 del 3. Cada uno normaliza la
entropía a su manera (`docs/21-sampler.md` §3.2) y mide su cobertura sobre su propia celda (§3.3,
nota del 16/09). Los tipos 4 y 5 entran en la semana 8; agregar uno es sumarlo a `REFRESHED_TYPES`
y darle su rama en `entropy_for` y en las celdas de cobertura.

Desde la semana 5 también **retira las honeypots** cuyo *pass rate* cayó bajo el umbral
(`docs/22-calidad-de-datos.md` §3.4), antes de contar nada.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LaneRole, Patch, Question, QuestionType, Response
from app.services import aggregable, answers, honeypots, questions
from app.services.questions import LANE_1V1_ROLES, Space

REFRESHED_TYPES: Final = (
    QuestionType.PAIRWISE_DIMENSION,
    QuestionType.PEAK_TIMING,
    QuestionType.LANE_MATCHUP,
)

#: El rango intercuartil que satura la entropía del tipo 2 (`docs/21-sampler.md` §3.2): con 12
#: minutos entre cuartiles la comunidad está tan dividida como puede estarlo para el sampler.
PEAK_IQR_SCALE: Final = 12

#: El colapso de la escala del tipo 3 a tres resultados. Vive en `answers` porque también lo usa la
#: consistencia del retest.
LANE_OUTCOME: Final = answers.LANE_OUTCOME

#: Una celda de cobertura: (campeón, dimensión), (campeón,) o (campeón, rol) según el tipo.
Cell = tuple[Any, ...]


@dataclass(slots=True)
class RefreshResult:
    """Lo que el comando de CLI imprime al terminar."""

    patch: str | None
    questions: int
    responses: int
    retired_honeypots: list[int] = field(default_factory=list)
    #: La mediana de cobertura de cada tipo; `None` si el tipo no tiene celdas.
    coverage_medians: dict[str, float | None] = field(default_factory=dict)


def _as_unit(value: float) -> Decimal:
    """Recorta a `[0, 1]` y fija cuatro decimales, que es lo que admiten las dos columnas.

    El máximo teórico de cada fórmula es exactamente 1, pero el redondeo del flotante puede
    devolver 1.0000000000000002, y `questions_entropy_range` y `questions_coverage_range` rechazan
    cualquier cosa fuera de `[0, 1]`. Sin este recorte el job falla contra la base en la mitad de
    los casos.
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
    return _as_unit(-p * math.log2(p) - (1 - p) * math.log2(1 - p))


def lane_entropy(counts: Mapping[str, int]) -> Decimal | None:
    """Entropía de Shannon sobre {gana A, parejo, gana B}, dividida por `log₂ 3`."""
    outcomes = {"a": 0, "even": 0, "b": 0}
    for key, count in counts.items():
        outcomes[LANE_OUTCOME[key]] += count
    total = sum(outcomes.values())
    if total == 0:
        return None
    shannon = -sum((n / total) * math.log2(n / total) for n in outcomes.values() if n)
    return _as_unit(shannon / math.log2(3))


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
    return _as_unit(min(1.0, (q3 - q1) / PEAK_IQR_SCALE))


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


# ------------------------------------------------------------------------------------ cobertura


def question_cells(
    question_type: QuestionType,
    champion_a: int,
    champion_b: int | None,
    dimension_id: int | None,
    role: LaneRole | str | None,
) -> list[Cell]:
    """Las celdas de cobertura que toca una pregunta (`docs/21-sampler.md` §3.3)."""
    match question_type:
        case QuestionType.PAIRWISE_DIMENSION:
            return [(c, dimension_id) for c in (champion_a, champion_b) if c is not None]
        case QuestionType.PEAK_TIMING:
            return [(champion_a,)]
        case QuestionType.LANE_MATCHUP if role is not None:
            lane = LaneRole(str(role))
            return [(c, lane) for c in (champion_a, champion_b) if c is not None]
        case _:
            return []


def pool_cells(question_type: QuestionType, space: Space) -> list[Cell]:
    """Las celdas del pool habilitado sobre las que se toma la mediana, ceros incluidos."""
    match question_type:
        case QuestionType.PAIRWISE_DIMENSION:
            return [(c, d) for c in space.champion_ids for d in space.dimension_ids]
        case QuestionType.PEAK_TIMING:
            return [(c,) for c in space.champion_ids]
        case QuestionType.LANE_MATCHUP:
            return [
                (champion.champion_id, role)
                for champion in space.champions
                for role in LANE_1V1_ROLES
                if role.value in {str(r) for r in champion.roles}
            ]
        case _:
            return []


def coverage_deficit(
    cells: Sequence[Cell], counts: Mapping[Cell, int], median: float | None
) -> Decimal | None:
    """El déficit del campeón peor cubierto de la pregunta (§3.3).

    Con mediana 0 —más de la mitad de las celdas vacías— no hay referencia contra la cual medir,
    y el déficit queda en `None`: el término vale 0 en la prioridad (nota del 16/09).
    """
    if not cells or median is None or median <= 0:
        return None
    worst = max(max(0.0, (median - counts.get(cell, 0)) / median) for cell in cells)
    return _as_unit(worst)


async def _coverage_counts(
    session: AsyncSession, patch_id: int
) -> dict[QuestionType, Counter[Cell]]:
    """Cuántas respuestas que entrarían a la agregación tiene cada celda.

    Son los `_n` crudos de `docs/25-agregacion.md` §5: en el tipo 1 sólo las decisivas, en los
    otros dos todas. Los filtros son los de 25 §1 (módulo `aggregable`).
    """
    threshold = await aggregable.min_trust(session)
    decisive = sa.or_(
        Question.type != QuestionType.PAIRWISE_DIMENSION,
        Response.answer["choice"].astext.in_(("a", "b")),
    )
    rows = await session.execute(
        sa.select(
            Question.type,
            Question.champion_a,
            Question.champion_b,
            Question.dimension_id,
            Question.role,
            sa.func.count(),
        )
        .select_from(aggregable.source())
        .where(
            Question.patch_id == patch_id,
            Question.type.in_(REFRESHED_TYPES),
            Question.champion_c.is_(None),
            decisive,
            *aggregable.conditions(threshold),
        )
        .group_by(
            Question.type,
            Question.champion_a,
            Question.champion_b,
            Question.dimension_id,
            Question.role,
        )
    )
    counts: dict[QuestionType, Counter[Cell]] = {t: Counter() for t in REFRESHED_TYPES}
    for question_type, a, b, dimension_id, role, total in rows.tuples():
        for cell in question_cells(question_type, a, b, dimension_id, role):
            counts[question_type][cell] += total
    return counts


# ----------------------------------------------------------------------------------------- job


async def _questions(
    session: AsyncSession, patch_id: int
) -> list[tuple[int, QuestionType, int, int | None, int | None, LaneRole | None]]:
    rows = await session.execute(
        sa.select(
            Question.question_id,
            Question.type,
            Question.champion_a,
            Question.champion_b,
            Question.dimension_id,
            Question.role,
        ).where(
            Question.patch_id == patch_id,
            Question.type.in_(REFRESHED_TYPES),
        )
    )
    return list(rows.tuples())


async def _counts_by_answer(session: AsyncSession, patch_id: int) -> dict[int, dict[str, int]]:
    """Un `GROUP BY` por pregunta y respuesta, sobre `responses_by_question`.

    La clave agrupada es el minuto en el tipo 2 y la opción elegida en los demás. Es la consulta
    cara del sistema, y por eso vive acá y no en el camino crítico.

    Las filas de retest no cuentan: son la misma persona contestando otra vez, y sumarlas
    inflaría el consenso y la exposición con una opinión repetida (`docs/25-agregacion.md` §1.3).
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
                Response.is_retest_of.is_(None),
            )
            .group_by(Response.question_id, key)
        )
    ).all()

    counts: dict[int, dict[str, int]] = {}
    for question_id, value, total in rows:
        counts.setdefault(question_id, {})[value] = total
    return counts


async def refresh(session: AsyncSession, now: dt.datetime | None = None) -> RefreshResult:
    """Retira honeypots, recalcula los denormalizados del parche vigente y hace commit.

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
    retired = await honeypots.retire_failing(session, patch.patch_id)

    space = await questions.load_space(session)
    coverage = await _coverage_counts(session, patch.patch_id)
    medians: dict[QuestionType, float | None] = {}
    for question_type in REFRESHED_TYPES:
        cells = pool_cells(question_type, space)
        values = [coverage[question_type].get(cell, 0) for cell in cells]
        medians[question_type] = float(statistics.median(values)) if values else None

    rows = await _questions(session, patch.patch_id)
    counts = await _counts_by_answer(session, patch.patch_id)

    payload: list[dict[str, Any]] = []
    for question_id, question_type, a, b, dimension_id, role in rows:
        answered = counts.get(question_id, {})
        cells = question_cells(question_type, a, b, dimension_id, role)
        payload.append(
            {
                "question_id": question_id,
                "answer_counts": answered,
                "exposure_count": sum(answered.values()),
                "entropy": entropy_for(question_type, answered),
                "coverage_deficit": coverage_deficit(
                    cells, coverage[question_type], medians[question_type]
                ),
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
        retired_honeypots=retired.retired,
        coverage_medians={t.value: m for t, m in medians.items()},
    )
