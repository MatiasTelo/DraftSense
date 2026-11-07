"""Bradley-Terry por la iteración MM de Hunter (2004), con el `ε` de `docs/25-agregacion.md` §5.1.

El pseudocódigo de §5.1 **es** la definición del estimador y esto lo implementa tal cual, sobre la
matriz densa de victorias ponderadas. `choix` no admite ese `ε` —un oponente virtual de fuerza 1
contra el que cada campeón tiene media victoria y media derrota— y por eso se usa sólo en el test,
con `ε = 0`, como verificación cruzada (§8.2, nota del 29/10).

La actualización es simultánea para todos los campeones. Tiene el mismo punto fijo que la
secuencial del pseudocódigo —el máximo de la verosimilitud penalizada— y se vectoriza.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def mm(W: FloatArray, eps: float, max_iter: int, tol: float) -> FloatArray:
    """Los scores `θ = log π`, con `π` normalizado a media geométrica 1 (θ de media 0).

    `W[i][j]` es el peso total de las respuestas donde se eligió a `i` frente a `j`. Con `ε = 0`
    un campeón invicto diverge: el `ε` es lo que lo mantiene finito y lo encoge hacia 0 (§5.1).
    """
    n = W.shape[0]
    N = W + W.T
    wins = W.sum(axis=1)
    pi = np.ones(n)
    for _ in range(max_iter):
        denominator = (N / (pi[:, None] + pi[None, :])).sum(axis=1) + 2 * eps / (pi + 1)
        updated = (wins + eps) / denominator
        updated /= np.exp(np.mean(np.log(updated)))
        change = np.max(np.abs(np.log(updated) - np.log(pi)))
        pi = updated
        if change < tol:
            break
    theta: FloatArray = np.log(pi)
    return theta
