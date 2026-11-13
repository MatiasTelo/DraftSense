"""Los parámetros de una corrida y la semilla del bootstrap (`docs/25-agregacion.md` §8.1, §9).

Todo parámetro sale, en este orden, de la línea de comandos, de `app_settings` o del valor inicial
de §9. **El que se registra en `exports` es el efectivamente usado**, nunca el default: es lo que
permite reproducir una corrida vieja pasando sus parámetros otra vez (CA-407, CA-408).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from aggregation import AGGREGATION_VERSION
from app.services import app_settings

#: Los valores iniciales de §9, por si `seed-settings` todavía no corrió en esa base.
DEFAULT_SUPPORT_THRESHOLDS: dict[str, dict[str, dict[str, float]]] = {
    "dimension": {"solid": {"n": 25, "width": 0.60}, "limited": {"n": 10, "width": 1.20}},
    "peak_minute": {"solid": {"n": 20, "width": 4}, "limited": {"n": 10, "width": 8}},
    "lane_strength": {"solid": {"n": 20, "width": 0.60}, "limited": {"n": 8, "width": 1.20}},
    "synergy": {"solid": {"n": 15, "width": 0.80}, "limited": {"n": 6, "width": 1.50}},
    "trait": {"solid": {"n": 20, "width": 0.25}, "limited": {"n": 10, "width": 0.45}},
}


@dataclass(frozen=True, slots=True)
class RunParams:
    patch_from: str
    patch_to: str
    min_trust: Decimal
    halflife: float
    sigma: float
    bootstrap: int
    exported_at: dt.date
    bt_prior: float
    lambda_champion: float
    lambda_interaction: float
    max_iter: int
    tol: float
    support_thresholds: dict[str, dict[str, dict[str, float]]]

    def __post_init__(self) -> None:
        """Los rangos sin los que la corrida se rompe a mitad de camino (§8.1, nota del 13/11).

        Vale para el CLI y para el panel, que arman los parámetros por acá. Con `halflife = 0` el
        peso divide por cero; con `min_trust = 0` entra quien tiene trust 0, su respuesta pesa
        cero —lo que §2.1 excluye: «ninguna respuesta admitida pesa cero»— y un campeón que sólo
        tenga de esas divide por la suma de pesos.
        """
        if not 0 < self.min_trust <= 1:
            raise ValueError("min_trust va entre 0 y 1, sin el 0")
        if not self.halflife > 0:
            raise ValueError("la vida media (halflife) tiene que ser mayor que 0")
        if not self.sigma > 0:
            raise ValueError("sigma tiene que ser mayor que 0")
        if self.bootstrap < 1:
            raise ValueError("bootstrap tiene que ser un entero positivo")

    @property
    def patch_window(self) -> str:
        return f"{self.patch_from}..{self.patch_to}"

    @property
    def seed(self) -> int:
        """La semilla de §4.2, derivada de los parámetros y nunca del reloj.

        Cada número entra con un formato fijo —`min_trust` con tres decimales, como lo guarda
        `exports.min_trust_applied`; la vida media y `σ` en su forma más corta—: `0.3` y `0.30`
        tienen que dar la misma semilla, o la misma corrida pedida de dos maneras daría dos
        resultados.
        """
        text = (
            f"{self.patch_window}|{self.min_trust:.3f}|{self.halflife:g}|{self.sigma:g}"
            f"|{self.bootstrap}|{AGGREGATION_VERSION}"
        )
        return int(hashlib.sha256(text.encode()).hexdigest()[:16], 16)

    def as_record(self) -> dict[str, Any]:
        """Todos los parámetros, para `exports.params` (`11-modelo-de-datos.md` §3.11)."""
        return {
            "patch_window": self.patch_window,
            "min_trust": f"{self.min_trust:.3f}",
            "decay_halflife_days": self.halflife,
            "power_sigma": self.sigma,
            "bootstrap_samples": self.bootstrap,
            "exported_at": self.exported_at.isoformat(),
            "bt_prior": self.bt_prior,
            "duo_lambda_champion": self.lambda_champion,
            "duo_lambda_interaction": self.lambda_interaction,
            "max_iter": self.max_iter,
            "tol": self.tol,
            "support_thresholds": self.support_thresholds,
            "seed": str(self.seed),
            "aggregation_version": AGGREGATION_VERSION,
        }


def parse_window(window: str) -> tuple[str, str]:
    """`16.18..16.20` → `("16.18", "16.20")`. Un parche solo vale como ventana de uno."""
    if ".." in window:
        start, end = window.split("..", 1)
    else:
        start = end = window
    if not start or not end:
        raise ValueError(f"ventana de parches inválida: {window!r}")
    return start.strip(), end.strip()


async def resolve(
    session: AsyncSession,
    *,
    patch_window: str | None,
    current_patch: str | None,
    min_trust: float | Decimal | None = None,
    halflife: float | None = None,
    sigma: float | None = None,
    bootstrap: int | None = None,
    exported_at: dt.date | None = None,
) -> RunParams:
    """CLI → `app_settings` → valor inicial (§8.2, paso 1)."""
    get = app_settings.get
    if patch_window is None:
        if current_patch is None:
            raise ValueError("no hay parche vigente: pasá --patch-window")
        patch_window = current_patch
    start, end = parse_window(patch_window)
    trust = min_trust if min_trust is not None else await get(session, "export.min_trust", 0.30)
    return RunParams(
        patch_from=start,
        patch_to=end,
        min_trust=Decimal(str(trust)).quantize(Decimal("0.001")),
        halflife=float(
            halflife
            if halflife is not None
            else await get(session, "aggregation.decay_halflife_days", 21)
        ),
        sigma=float(
            sigma if sigma is not None else await get(session, "aggregation.power_sigma", 7.5)
        ),
        bootstrap=int(
            bootstrap
            if bootstrap is not None
            else await get(session, "aggregation.bootstrap_samples", 2000)
        ),
        # En UTC, como la fecha de cada respuesta en `load.weight`: con la fecha local, una
        # corrida nocturna en UTC−3 quedaba un día atrás de las respuestas de esa noche.
        exported_at=exported_at or dt.datetime.now(dt.UTC).date(),
        bt_prior=float(await get(session, "aggregation.bt_prior", 0.5)),
        lambda_champion=float(await get(session, "aggregation.duo_lambda_champion", 0.10)),
        lambda_interaction=float(await get(session, "aggregation.duo_lambda_interaction", 1.00)),
        max_iter=int(await get(session, "aggregation.max_iter", 500)),
        tol=float(await get(session, "aggregation.tol", 1e-9)),
        support_thresholds=await get(
            session, "aggregation.support_thresholds", DEFAULT_SUPPORT_THRESHOLDS
        ),
    )
