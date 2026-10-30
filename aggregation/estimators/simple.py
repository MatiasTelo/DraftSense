"""Los dos estimadores sin modelo: la mediana ponderada del pico (§5.2) y la proporción con
intervalo de Wilson de los atributos (§5.6)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike

#: z de un intervalo del 95 %.
Z95 = 1.959963984540054


def weighted_median(values: ArrayLike, weights: ArrayLike) -> float:
    """§5.2: se ordena, se acumulan los pesos y se toma el valor donde el acumulado alcanza la
    mitad; si cae exactamente en el borde entre dos valores, se promedian los dos."""
    order = np.argsort(np.asarray(values, dtype=np.float64), kind="stable")
    sorted_values = np.asarray(values, dtype=np.float64)[order]
    cumulative = np.cumsum(np.asarray(weights, dtype=np.float64)[order])
    half = cumulative[-1] / 2
    index = int(np.searchsorted(cumulative, half))
    if math.isclose(cumulative[index], half, rel_tol=1e-12) and index + 1 < len(sorted_values):
        return float((sorted_values[index] + sorted_values[index + 1]) / 2)
    return float(sorted_values[index])


def round_half_up(value: float) -> int:
    """`round()` redondea al par (26,5 → 26). El pico se publica con el medio hacia arriba."""
    return math.floor(value + 0.5)


def power_at(minute: float, peak: int, sigma: float) -> float:
    """ADR-009, sobre el pico entero ya exportado para que el CSV se pueda recalcular."""
    return math.exp(-((minute - peak) ** 2) / (2 * sigma**2))


def wilson(p: float, n: float) -> tuple[float, float]:
    """Intervalo de Wilson al 95 %. `n` es el tamaño efectivo de Kish, no el conteo (§5.6)."""
    z2 = Z95**2
    denominator = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    half = Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n**2)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def kish(weights: Sequence[float]) -> float:
    """`(Σ w)² / Σ w²`: con pesos desiguales es menor que el conteo."""
    total = sum(weights)
    return total**2 / sum(w * w for w in weights)
