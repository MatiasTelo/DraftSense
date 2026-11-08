"""Estabilidad por segmento (`docs/25-agregacion.md` §3.5 y `docs/27-...` §7.2).

El mismo ajuste de las 8 dimensiones, con los mismos parámetros, sobre las respuestas de cada
segmento; y los segmentos se comparan **entre sí**, no contra el global, que los contiene.

**Un segmento bajo el piso no da números.** Con menos de 15 respondedores o 300 comparaciones en
esa dimensión se reporta *no calculable* con su `n`: con el volumen del piloto es un desenlace
probable, y un ρ sobre veinte comparaciones sería un número frágil con cara de hallazgo.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

import numpy as np
from scipy.stats import spearmanr

from aggregation.fits import DimensionResult
from aggregation.load import Row
from aggregation.quality.data import Person
from app.models import QuestionType
from app.models.collection import VALID_HOURS_BUCKETS

UNDECLARED = "undeclared"

#: Los cinco segmentos de rango de 25 §3.5.
RANK_SEGMENTS: dict[str, tuple[str, ...]] = {
    "low": ("iron", "bronze", "silver"),
    "mid": ("gold", "platinum", "emerald"),
    "high": ("diamond", "master", "grandmaster", "challenger"),
    "unranked": ("unranked",),
}

#: Las horas, tal cual: 25 §3.5 pide «el mismo análisis» y no agrupa buckets (27 §7.2).
HOURS_SEGMENTS: dict[str, tuple[str, ...]] = {bucket: (bucket,) for bucket in VALID_HOURS_BUCKETS}

#: Las dos variables ordenadas, en el orden del informe.
VARIABLES: dict[str, dict[str, tuple[str, ...]]] = {"rank": RANK_SEGMENTS, "hours": HOURS_SEGMENTS}

#: El disparador de 25 §3.10: ρ entre `low` y `high` bajo esto en tantas dimensiones o más.
TRIGGER_RHO = 0.70
TRIGGER_DIMENSIONS = 3


def names(variable: str) -> list[str]:
    return [*VARIABLES[variable], UNDECLARED]


def segment_of(variable: str, person: Person | None) -> str:
    value = None
    if person is not None:
        value = person.rank if variable == "rank" else person.hours
    if value is None:
        return UNDECLARED
    for name, members in VARIABLES[variable].items():
        if value in members:
            return name
    raise ValueError(f"{variable} fuera del esquema: {value!r}")


@dataclass(frozen=True, slots=True)
class Size:
    respondents: int
    comparisons: int
    calculable: bool


def subset(
    rows: Sequence[Row],
    dimension_id: int,
    variable: str,
    segment: str,
    people: Mapping[uuid.UUID, Person],
) -> list[Row]:
    """Las filas del tipo 1 de esa dimensión que contestó alguien de ese segmento."""
    return [
        r
        for r in rows
        if r.type is QuestionType.PAIRWISE_DIMENSION
        and r.dimension_id == dimension_id
        and segment_of(variable, people.get(r.respondent_id)) == segment
    ]


def size(rows: Sequence[Row], min_respondents: int, min_comparisons: int) -> Size:
    """Lo que cuenta para el piso: comparaciones decisivas y quiénes las hicieron (§3.5, 4)."""
    decisive = [r for r in rows if r.answer.get("choice") in ("a", "b")]
    people = len({r.respondent_id for r in decisive})
    return Size(
        respondents=people,
        comparisons=len(decisive),
        calculable=people >= min_respondents and len(decisive) >= min_comparisons,
    )


@dataclass(frozen=True, slots=True)
class Comparison:
    first: str
    second: str
    #: Campeones del pool con valor en los dos segmentos.
    common: int
    rho: float | None
    mean_abs_diff: float | None
    support_changes: int


def compare(
    first: DimensionResult, second: DimensionResult, pool: Sequence[int]
) -> tuple[int, float | None, float | None, int]:
    common = [
        c
        for c in pool
        if first.estimates[c].value is not None and second.estimates[c].value is not None
    ]
    changes = sum(1 for c in common if first.estimates[c].support != second.estimates[c].support)
    if not common:
        return 0, None, None, 0
    a = np.array([first.estimates[c].value for c in common], dtype=np.float64)
    b = np.array([second.estimates[c].value for c in common], dtype=np.float64)
    diff = float(np.mean(np.abs(a - b)))
    rho: float | None = None
    if len(common) >= 3 and np.ptp(a) > 0 and np.ptp(b) > 0:
        value = float(spearmanr(a, b).statistic)
        rho = None if math.isnan(value) else value
    return len(common), rho, diff, changes


def comparisons(
    results: Mapping[str, DimensionResult], order: Sequence[str], pool: Sequence[int]
) -> list[Comparison]:
    """Todos los pares de segmentos calculables, en el orden de la variable."""
    present = [name for name in order if name in results]
    out = []
    for first, second in combinations(present, 2):
        common, rho, diff, changes = compare(results[first], results[second], pool)
        out.append(Comparison(first, second, common, rho, diff, changes))
    return out


def triggered(rank_comparisons: Mapping[str, Sequence[Comparison]]) -> list[str]:
    """Las dimensiones donde ρ(`low`, `high`) < 0.70. Si son tres o más, es el hallazgo de §3.10."""
    low = []
    for code, items in rank_comparisons.items():
        for item in items:
            pair = {item.first, item.second}
            if pair == {"low", "high"} and item.rho is not None and item.rho < TRIGGER_RHO:
                low.append(code)
    return low
