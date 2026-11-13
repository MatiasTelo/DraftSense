"""La aplicación ASGI.

`uvicorn app.main:app --reload` en desarrollo. La OpenAPI se genera sola desde los schemas de
Pydantic y queda en `/docs`: **si el contrato y `docs/12-api.md` divergen, manda el código y el
documento está desactualizado** (`docs/12-api.md`, encabezado).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import get_engine
from app.errors import register_error_handlers
from app.routers import health, profile, questions, responses, sessions

API_PREFIX = "/api/v1"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Cierra el pool al terminar.

    Sin el `dispose()`, cada recarga de `--reload` deja conexiones abiertas contra el pooler de
    Supabase hasta agotar su cupo, y el síntoma aparece recién varios reinicios después.
    """
    if not get_settings().ip_hash_salt:
        # Sin sal no se guarda `respondents.ip_hash` y la mitad «por hash de IP» de RF-209 queda
        # apagada (ADR-033). En desarrollo es esperable; en producción es un error de despliegue.
        logger.warning("DS_IP_HASH_SALT no está configurada: el límite de tasa por IP no se aplica")
    yield
    await get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="DraftSense API",
        version="1",
        description="Etiquetado crowdsourced de campeones de League of Legends.",
        lifespan=lifespan,
    )

    # El origen es el dominio concreto, NUNCA `*`: con `allow_credentials=True` el comodín es
    # inválido por especificación y la cookie de sesión no viajaría (`docs/12-api.md` §5).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "X-Client-Fingerprint"],
    )

    register_error_handlers(app)

    for module in (health, sessions, questions, responses, profile):
        app.include_router(module.router, prefix=API_PREFIX)

    return app


app = create_app()
