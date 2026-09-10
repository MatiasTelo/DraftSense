"""El sobre de error del contrato y los manejadores que garantizan que nada se escape de él.

Toda respuesta de error de la API tiene la misma forma (`docs/12-api.md` §3):

    {"error": {"code": "...", "message": "...", "field": "..."}}

Devolver un `HTTPException` de FastAPI a mano produce `{"detail": ...}` y **rompe el contrato en
silencio**, porque el cliente no valida la forma del error: simplemente no encuentra `error.code`
y muestra un mensaje genérico. Por eso los errores se levantan con `ApiError` y por eso están
registrados los manejadores de las tres excepciones que el framework produce por su cuenta.

Ver ADR-015.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError

#: El índice único parcial que impone el 409. La restricción vive en la base y no en el código
#: para que dos requests simultáneos no puedan insertar dos filas (docs/12-api.md §3).
DUPLICATE_RESPONSE_INDEX = "responses_one_per_question"


class ApiError(Exception):
    """Un error del contrato. `code` tiene que estar tabulado en `docs/12-api.md` §3."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        field: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field = field
        #: Cabeceras que tiene que llevar la respuesta de error. Van acá y no en el `Response`
        #: inyectado en el endpoint porque el manejador construye la respuesta de cero: lo que
        #: se haya puesto en aquél se pierde al levantar la excepción. Es el caso de
        #: `Retry-After` y de las `X-RateLimit-*` de un 429.
        self.headers = headers


def error_body(code: str, message: str, field: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if field is not None:
        body["field"] = field
    return {"error": body}


def _response(
    status_code: int, code: str, message: str, field: str | None = None, **kwargs: Any
) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error_body(code, message, field), **kwargs)


async def _handle_api_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    if exc.headers:
        return _response(exc.status_code, exc.code, exc.message, exc.field, headers=exc.headers)
    return _response(exc.status_code, exc.code, exc.message, exc.field)


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    """El 422 de Pydantic, traducido al sobre del contrato."""
    assert isinstance(exc, RequestValidationError)
    first = exc.errors()[0] if exc.errors() else None
    # `loc` es ('body', 'campo') o ('query', 'campo'); al cliente le sirve el último tramo.
    field = str(first["loc"][-1]) if first and first.get("loc") else None
    message = str(first["msg"]) if first else "request validation failed"
    # 422. La constante de Starlette se renombró; el número es el que fija el contrato.
    return _response(422, "validation_error", message, field)


async def _handle_integrity_error(_: Request, exc: Exception) -> JSONResponse:
    """Una violación de restricción única se traduce, el resto se deja explotar.

    Sólo se convierte la del índice de respuesta duplicada. Cualquier otra `IntegrityError` es un
    bug —una FK rota, un CHECK que el código debió validar antes— y esconderla detrás de un 409
    haría que se descubriera en producción y no en los tests.
    """
    assert isinstance(exc, IntegrityError)
    if DUPLICATE_RESPONSE_INDEX not in str(exc.orig):
        raise exc
    return _response(
        status.HTTP_409_CONFLICT,
        "duplicate_response",
        "this question was already answered by this respondent",
        "question_id",
    )


async def _handle_dbapi_error(_: Request, exc: Exception) -> JSONResponse:
    """La base no responde: 503, y la SPA muestra reintento (`docs/10-arquitectura.md` §7)."""
    assert isinstance(exc, DBAPIError)
    return _response(
        status.HTTP_503_SERVICE_UNAVAILABLE, "database_unavailable", "the database is unavailable"
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    # El orden importa: IntegrityError es subclase de DBAPIError y tiene que registrarse antes.
    app.add_exception_handler(IntegrityError, _handle_integrity_error)
    app.add_exception_handler(DBAPIError, _handle_dbapi_error)
