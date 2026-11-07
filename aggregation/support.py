"""`_support` a partir de `_n` y del ancho del intervalo (`docs/26-esquema-de-salida.md` §2.4).

Los umbrales son los de `aggregation.support_thresholds`: cada nivel exige **las dos**
condiciones, y lo que no llega a `limited` es `insufficient`. Qué juego usa cada magnitud está en
`docs/25-agregacion.md` §4.4: el `matchup_matrix` usa el de fuerza de línea y la línea de dupla, el
de sinergia.
"""

from __future__ import annotations

from collections.abc import Mapping

SOLID = "solid"
LIMITED = "limited"
INSUFFICIENT = "insufficient"


def level(
    thresholds: Mapping[str, Mapping[str, Mapping[str, float]]],
    kind: str,
    n: int,
    low: float | None,
    high: float | None,
) -> str:
    if low is None or high is None:
        return INSUFFICIENT
    width = high - low
    for name in (SOLID, LIMITED):
        rule = thresholds[kind][name]
        if n >= rule["n"] and width <= rule["width"]:
            return name
    return INSUFFICIENT
