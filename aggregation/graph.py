"""Componentes conexas del grafo de comparaciones ([ADR-008], `docs/25-agregacion.md` §7).

Dos campeones están unidos si aparecen en una misma comparación. Si el grafo está partido no se
inventa un orden entre las partes: cada componente se ajusta y se centra por separado, y lo que
queda fuera de la mayor sale `insufficient`.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

IntArray = NDArray[np.int64]


def components(n: int, first: IntArray, second: IntArray) -> IntArray:
    """La etiqueta de componente de cada uno de los `n` nodos. Uno sin aristas es su propia
    componente."""
    graph = coo_matrix((np.ones(len(first)), (first, second)), shape=(n, n))
    _, labels = connected_components(graph, directed=False)
    return np.asarray(labels, dtype=np.int64)


def largest(labels: IntArray, active: NDArray[np.bool_]) -> int | None:
    """La etiqueta de la componente con más nodos activos. Empata la de etiqueta menor."""
    if not active.any():
        return None
    counts = np.bincount(labels[active])
    return int(np.argmax(counts))


def preserved(
    labels: IntArray, active: NDArray[np.bool_], first: IntArray, second: IntArray
) -> bool:
    """Si un remuestreo conserva las componentes originales (§8.2, nota del 29/10).

    El remuestreo usa un subconjunto de las aristas originales, así que su partición refina la
    original: alcanza con contar. Se descarta si algún nodo activo se quedó sin aristas o si alguna
    componente se partió.
    """
    n = len(labels)
    touched = np.zeros(n, dtype=bool)
    touched[first] = True
    touched[second] = True
    if not touched[active].all():
        return False
    resampled = components(n, first, second)
    return len(set(resampled[active].tolist())) == len(set(labels[active].tolist()))
