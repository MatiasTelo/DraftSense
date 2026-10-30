"""La aplicación ASGI del panel (ADR-025).

Se levanta con `python -m draftsense_admin`, que fija el host en `127.0.0.1`. Este módulo agrega
una segunda barrera por si alguien la levanta a mano con `uvicorn --host 0.0.0.0`: todo pedido que
no venga de la propia máquina recibe `403`. Sin clave, esa es la única protección que tiene el
panel, y no puede depender de que el comando de arranque sea el correcto.
"""

from __future__ import annotations

import ipaddress
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse

from app.errors import error_body
from draftsense_admin.config import get_admin_settings
from draftsense_admin.db import get_engine, get_sessionmaker
from draftsense_admin.errors import register_admin_error_handlers
from draftsense_admin.routers import jobs, monitoring, operations
from draftsense_admin.services.exporting import ExportRunner
from draftsense_admin.services.jobs import JobRunner

API_PREFIX = "/api"


def is_loopback(host: str | None) -> bool:
    if host is None:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        # El cliente de pruebas de Starlette se presenta como "testclient".
        return host == "testclient"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await get_engine().dispose()


def create_app(static_dir: Path | None = None) -> FastAPI:
    app = FastAPI(
        title="DraftSense — administración",
        version="1",
        description="App de administración local del servidor del laboratorio (ADR-025).",
        lifespan=lifespan,
    )
    app.state.job_runner = JobRunner(lambda: get_sessionmaker()())
    app.state.export_runner = ExportRunner(
        lambda: get_sessionmaker()(), get_admin_settings().exports_dir
    )

    @app.middleware("http")
    async def only_this_machine(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        host = request.client.host if request.client else None
        if not is_loopback(host):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=error_body(
                    "local_only", "el panel sólo atiende desde la máquina del servidor"
                ),
            )
        return await call_next(request)

    register_admin_error_handlers(app)
    for module in (monitoring, operations, jobs):
        app.include_router(module.router, prefix=API_PREFIX)

    root = static_dir if static_dir is not None else get_admin_settings().static_dir

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> Response:
        """El build del frontend. Toda ruta que no es un archivo devuelve `index.html`: las rutas
        del panel (`/conectividad`, `/pool`…) las resuelve React Router en el navegador."""
        if path.startswith("api/") or path == "api":
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=error_body("not_found", "no existe ese endpoint"),
            )
        index = root / "index.html"
        if not index.is_file():
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=error_body(
                    "frontend_not_built",
                    "falta el build del frontend: corré `npm run build` en admin/frontend",
                ),
            )
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root.resolve()):
            return FileResponse(candidate)
        return FileResponse(index)

    return app


app = create_app()
