"""El alfa de Krippendorff (`docs/27-validacion-confiabilidad.md` §2.2).

Se implementa acá, con la matriz de coincidencias, en vez de sumar una dependencia: son treinta
líneas, y el test lo compara contra el ejemplo resuelto de Krippendorff (2011) con sus valores
publicados (CA-410).

**Alfa no se inventa.** Con menos de dos valores aparejables, o con todos los valores iguales, el
denominador no existe y la función devuelve `None`. El informe dice *no calculable* con su `n`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

Scale = Literal["nominal", "ordinal", "interval"]


@dataclass(frozen=True, slots=True)
class Alpha:
    #: `None` si no está definido (§2.2).
    value: float | None
    #: Valores aparejables: los de las unidades con al menos dos.
    pairable: int
    #: Unidades con al menos dos valores.
    units: int


def _distances(
    categories: Sequence[Hashable], marginals: NDArray[np.float64], scale: Scale
) -> NDArray[np.float64]:
    size = len(categories)
    if scale == "nominal":
        return 1.0 - np.eye(size)
    if scale == "interval":
        values = np.array([float(c) for c in categories])  # type: ignore[arg-type]
        return np.asarray(np.subtract.outer(values, values) ** 2, dtype=np.float64)
    # Ordinal: la masa de las categorías entre c y k, menos la mitad de las dos puntas.
    cumulative = np.concatenate([[0.0], np.cumsum(marginals)])
    delta = np.zeros((size, size))
    for c in range(size):
        for k in range(size):
            low, high = min(c, k), max(c, k)
            between = cumulative[high + 1] - cumulative[low]
            delta[c, k] = (between - (marginals[c] + marginals[k]) / 2) ** 2
    return delta


def alpha(
    units: Iterable[Sequence[Hashable]],
    scale: Scale,
    categories: Sequence[Hashable] | None = None,
) -> Alpha:
    """Alfa sobre `units`, cada una con los valores que recibió.

    `categories` fija el orden de la escala: es obligatorio en la ordinal, donde el orden es el
    dato. En las otras dos, si falta, se usan los valores observados ordenados.
    """
    counted = [Counter(values) for values in units]
    counted = [c for c in counted if sum(c.values()) >= 2]
    if categories is None:
        if scale == "ordinal":
            raise ValueError("la escala ordinal necesita el orden de las categorías")
        categories = sorted({v for c in counted for v in c})  # type: ignore[type-var]
    index = {c: i for i, c in enumerate(categories)}
    size = len(categories)

    coincidences = np.zeros((size, size))
    for counts in counted:
        m = sum(counts.values())
        vector = np.zeros(size)
        for value, count in counts.items():
            vector[index[value]] = count
        coincidences += (np.outer(vector, vector) - np.diag(vector)) / (m - 1)

    # Cada valor de una unidad aparejable suma exactamente 1 a los marginales: `n` es entero.
    pairable = sum(sum(c.values()) for c in counted)
    marginals = coincidences.sum(axis=1)
    n = float(pairable)
    if pairable < 2:
        return Alpha(None, pairable, len(counted))
    delta = _distances(categories, marginals, scale)
    observed = float((coincidences * delta).sum())
    expected = float((np.outer(marginals, marginals) * delta).sum())
    if expected == 0:
        return Alpha(None, pairable, len(counted))
    return Alpha(1.0 - (n - 1) * observed / expected, pairable, len(counted))
