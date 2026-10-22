"""Motor y sesiones de la app admin.

No reutiliza `app.db`: ese módulo construye el motor con la configuración de `backend/.env`, y el
admin tiene que conectarse con la suya. Los services del backend reciben una `AsyncSession` y no
saben de dónde vino, así que alcanza con dársela.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from draftsense_admin.config import get_admin_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_admin_settings().database_url, pool_pre_ping=True)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependencia de FastAPI: una sesión por request."""
    async with get_sessionmaker()() as session:
        yield session
