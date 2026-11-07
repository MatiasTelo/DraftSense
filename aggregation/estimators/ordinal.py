"""El modelo ordinal de Rao-Kupper con umbrales simétricos (`docs/25-agregacion.md` §5.3 a §5.5).

Con `δ = fuerza(a) − fuerza(b)` y los niveles ordenados de «gana b por mucho» (0) a «gana a por
mucho» (K−1):

    P(Y ≥ k) = σ(δ − t_k)        t = (−τ₂, −τ₁, τ₁, τ₂) con cinco niveles, (−τ, τ) con tres

que es exactamente la tabla de §5.3 y, con tres niveles, la de §5.5. Se estima por máxima
verosimilitud ponderada con L-BFGS sobre `(fuerzas, log τ₁, log(τ₂ − τ₁))`, que impone
`0 < τ₁ < τ₂` sin restricciones explícitas.

Las fuerzas son lineales en los parámetros: `δ = D · x`, con `D` disperso. En el 1v1 cada fila
tiene un `+1` y un `−1`; en las duplas, `+1` en los dos efectos de campeón y la interacción de la
dupla de arriba y `−1` en los de la de abajo (§5.4). La penalización la elige quien llama: el `ε`
de §5.1 en el 1v1, L2 en las duplas.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize
from scipy.sparse import csr_matrix
from scipy.special import expit

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

#: El margen de cada nivel del 1v1, de «gana b por mucho» a «gana a por mucho» (26 §4).
LANE_VALUES = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])

#: Penalización: devuelve (valor, gradiente) sobre las fuerzas.
Penalty = Callable[[FloatArray], tuple[float, FloatArray]]

#: Lo mínimo que puede valer una probabilidad dentro del logaritmo: con 0 el ajuste diverge.
_FLOOR = 1e-300


@dataclass(frozen=True, slots=True)
class OrdinalFit:
    strengths: FloatArray
    thresholds: FloatArray


def thresholds(z: FloatArray, levels: int) -> FloatArray:
    """`t` ascendente a partir de los parámetros libres."""
    if levels == 5:
        tau1 = np.exp(z[0])
        tau2 = tau1 + np.exp(z[1])
        return np.array([-tau2, -tau1, tau1, tau2])
    tau = np.exp(z[0])
    return np.array([-tau, tau])


def probabilities(delta: FloatArray, t: FloatArray) -> FloatArray:
    """`P(Y = k | δ)` para cada fila de `delta` y cada nivel, como matriz `(len(δ), K)`."""
    exceed = expit(delta[:, None] - t[None, :])
    ones = np.ones((len(delta), 1))
    zeros = np.zeros((len(delta), 1))
    cumulative = np.hstack([ones, exceed, zeros])
    result: FloatArray = cumulative[:, :-1] - cumulative[:, 1:]
    return result


def _objective(
    x: FloatArray,
    D: csr_matrix,
    y: IntArray,
    w: FloatArray,
    levels: int,
    penalty: Penalty,
) -> tuple[float, FloatArray]:
    p = D.shape[1]
    strengths, z = x[:p], x[p:]
    t = thresholds(z, levels)
    delta = D @ strengths
    # G_k = P(Y ≥ k), con G_0 = 1 y G_K = 0; g_k es su derivada respecto de δ.
    G = np.hstack([np.ones((len(y), 1)), expit(delta[:, None] - t[None, :]), np.zeros((len(y), 1))])
    g = G * (1 - G)
    rows = np.arange(len(y))
    upper, lower = G[rows, y], G[rows, y + 1]
    prob = np.maximum(upper - lower, _FLOOR)
    loglik = float(np.sum(w * np.log(prob)))

    d_delta = w * (g[rows, y] - g[rows, y + 1]) / prob
    grad_strengths = D.T @ d_delta
    # ∂ℓ/∂t_k: el umbral k entra con signo − en P(Y = k) y con signo + en P(Y = k − 1).
    d_t = np.zeros(levels - 1)
    for k in range(1, levels):
        own = y == k
        below = y + 1 == k
        d_t[k - 1] = np.sum(w[own] * -g[own, k] / prob[own]) + np.sum(
            w[below] * g[below, k] / prob[below]
        )
    if levels == 5:
        tau1 = np.exp(z[0])
        gap = np.exp(z[1])
        outer = -d_t[0] + d_t[3]
        inner = -d_t[1] + d_t[2]
        grad_z = np.array([tau1 * (inner + outer), gap * outer])
    else:
        tau = np.exp(z[0])
        grad_z = np.array([tau * (-d_t[0] + d_t[1])])

    pen, pen_grad = penalty(strengths)
    value = -loglik + pen
    gradient = np.concatenate([-grad_strengths + pen_grad, -grad_z])
    return value, gradient


def fit(
    D: csr_matrix,
    y: IntArray,
    w: FloatArray,
    levels: int,
    penalty: Penalty,
    max_iter: int,
    tol: float,
    start: FloatArray | None = None,
) -> OrdinalFit:
    """Máxima verosimilitud ponderada. `start` permite arrancar el bootstrap desde el ajuste
    completo: llega al mismo óptimo en menos iteraciones."""
    p = D.shape[1]
    z0 = np.log([0.5, 0.5]) if levels == 5 else np.log([0.5])
    x0 = start if start is not None else np.concatenate([np.zeros(p), z0])
    result = minimize(
        _objective,
        x0,
        args=(D, y, w, levels, penalty),
        jac=True,
        method="L-BFGS-B",
        options={"maxiter": max_iter, "ftol": tol, "gtol": tol},
    )
    x = np.asarray(result.x, dtype=np.float64)
    return OrdinalFit(strengths=x[:p], thresholds=x[p:])


def epsilon_prior(eps: float) -> Penalty:
    """El `ε` de §5.1: media victoria y media derrota contra un oponente de fuerza 0."""

    def penalty(theta: FloatArray) -> tuple[float, FloatArray]:
        value = -eps * float(np.sum(np.log(expit(theta)) + np.log(expit(-theta))))
        return value, eps * (2 * expit(theta) - 1)

    return penalty


def ridge(weights: FloatArray) -> Penalty:
    """L2 con un `λ` por parámetro (§5.4): `Σ λ_j · x_j²`."""

    def penalty(x: FloatArray) -> tuple[float, FloatArray]:
        return float(np.sum(weights * x**2)), 2 * weights * x

    return penalty


def advantage(delta: FloatArray, z: FloatArray) -> FloatArray:
    """El margen esperado de §5.3, `Σ v_k · P(Y = k | δ)`, en `(−1, +1)`."""
    result: FloatArray = probabilities(delta, thresholds(z, 5)) @ LANE_VALUES
    return result
