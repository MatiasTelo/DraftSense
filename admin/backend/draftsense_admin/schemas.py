"""Los cuerpos de los pedidos del contrato interno (`docs/24-panel-admin.md` §5).

Las respuestas son los diccionarios que arman los services: el contrato no es público y cambia con
el panel, así que duplicarlo en modelos de respuesta sería mantener dos copias de lo mismo.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Body(BaseModel):
    # Un campo mal escrito en el frontend tiene que fallar, no ignorarse: `force` con una letra de
    # menos activaría sin forzar y el error parecería otro.
    model_config = ConfigDict(extra="forbid")


class FlagIn(_Body):
    flagged: bool
    reason: str = Field(min_length=1)


class PoolTierIn(_Body):
    champion_ids: list[int] = Field(min_length=1)
    pool_tier: int


class SettingIn(_Body):
    #: Cualquier JSON válido (24 §3.6).
    value: Any


class ActivateIn(_Body):
    force: bool = False


class JobIn(_Body):
    params: dict[str, Any] = Field(default_factory=dict)


class ChampionsSeedIn(_Body):
    version: str = Field(min_length=1)
    ddragon_version: str | None = None
    released_at: dt.date | None = None
    use_snapshot: bool = False


class PickRateSeedIn(_Body):
    version: str = Field(min_length=1)
    file: str
    source: str = "lolalytics"
    source_url: str = Field(min_length=1)
    captured_at: dt.date
    released_at: dt.date | None = None
    notes: str | None = None


class HoneypotsSeedIn(_Body):
    version: str = Field(min_length=1)
    file: str
    force: bool = False
