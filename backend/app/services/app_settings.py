"""Lectura de los parámetros operativos, con caché en proceso.

`app_settings` son unas 33 filas que se leen en casi cada petición y cambian dos veces por semana.
Consultarlas cada vez sería una ida a la base en el camino crítico; cachearlas para siempre haría
que un cambio del panel no tuviera efecto hasta el próximo despliegue, que es exactamente lo que
RF-606 prohíbe. El acuerdo es una caché de 60 segundos (`docs/11-modelo-de-datos.md` §3.12).
"""

from __future__ import annotations

import time
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSetting

CACHE_TTL_SECONDS = 60.0

_cache: dict[str, Any] | None = None
_loaded_at = 0.0


def reset_cache() -> None:
    """Vacía la caché. La usan los tests y el panel después de un `PATCH /admin/settings`."""
    global _cache, _loaded_at
    _cache = None
    _loaded_at = 0.0


async def load_all(session: AsyncSession) -> dict[str, Any]:
    global _cache, _loaded_at
    now = time.monotonic()
    if _cache is None or now - _loaded_at > CACHE_TTL_SECONDS:
        rows = (await session.execute(sa.select(AppSetting.key, AppSetting.value))).all()
        _cache = {key: value for key, value in rows}
        _loaded_at = now
    return _cache


async def get[T](session: AsyncSession, key: str, default: T) -> T | Any:
    """El valor de una clave, o `default` si todavía no se sembró.

    El default existe para que un entorno recién migrado —sin `seed-settings` corrido— arranque
    igual, no para que el valor viva en el código: el del seed es el que manda.
    """
    return (await load_all(session)).get(key, default)
