"""Errores del contrato interno (`docs/24-panel-admin.md` §5).

Mismo sobre que la API pública, con un campo opcional más: `details`, la lista de problemas
cuando hay más de uno (los faltantes de un parche, los errores de un archivo de seed). Se reusan
los manejadores de `app.errors` para todo lo demás, así que un 422 de Pydantic o una base caída
salen igual que en la API pública.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.errors import ApiError, error_body, register_error_handlers


class AdminError(ApiError):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        field: str | None = None,
        details: list[str] | None = None,
    ) -> None:
        super().__init__(code, message, status_code, field)
        self.details = details


async def _handle_admin_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AdminError)
    body = error_body(exc.code, exc.message, exc.field)
    if exc.details:
        body["error"]["details"] = exc.details
    return JSONResponse(status_code=exc.status_code, content=body)


def register_admin_error_handlers(app: FastAPI) -> None:
    register_error_handlers(app)
    # Starlette busca el manejador por la MRO de la excepción: el de la subclase gana.
    app.add_exception_handler(AdminError, _handle_admin_error)
