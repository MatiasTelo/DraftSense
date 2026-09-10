"""Dependencias de FastAPI: identidad del respondedor y autorización del panel.

Es la única capa que traduce entre HTTP y el dominio: de acá para adentro los services reciben un
`Respondent`, no una `Request`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.errors import ApiError
from app.models import Respondent
from app.services import sessions

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def client_ip(request: Request) -> str | None:
    """La IP del cliente, mirando primero el proxy.

    Detrás de Fly.io la IP real viaja en `X-Forwarded-For`; `request.client.host` sería la del
    balanceador y agruparía a todos los usuarios en una sola huella.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=sessions.COOKIE_NAME,
        value=token,
        max_age=sessions.COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


@dataclass(slots=True)
class CurrentSession:
    """El respondedor de esta petición y si hubo que crearlo."""

    respondent: Respondent
    created: bool


async def resolve_session(
    request: Request,
    response: Response,
    session: SessionDep,
    x_client_fingerprint: Annotated[str | None, Header()] = None,
) -> CurrentSession:
    """Devuelve el respondedor de la cookie, creándolo si no hay uno válido.

    **No tener sesión no es un error**, es el estado inicial de todo visitante: se crea una y se
    devuelve la cookie, igual que haría `POST /sessions` (`docs/12-api.md` §1.3). Devolver un 401
    obligaría al cliente a un viaje de red extra para llegar al mismo lugar.
    """
    token = request.cookies.get(sessions.COOKIE_NAME)
    respondent = await sessions.find_by_token(session, token)
    if respondent is not None:
        # Deliberadamente NO se toca `last_seen` acá. La racha de respuestas se corta comparando
        # `now() - last_seen` contra los 30 minutos (`docs/23-gamificacion.md` §2.1): si la
        # dependencia lo actualizara, la diferencia sería siempre cero y la racha no se cortaría
        # nunca. Lo actualizan `POST /sessions` y `POST /responses`, que son los dos puntos donde
        # el documento lo pide.
        return CurrentSession(respondent=respondent, created=False)

    fingerprint = sessions.build_fingerprint(
        x_client_fingerprint, request.headers.get("user-agent"), client_ip(request)
    )
    respondent, new_token = await sessions.create(session, fingerprint)
    set_session_cookie(response, new_token)
    return CurrentSession(respondent=respondent, created=True)


CurrentSessionDep = Annotated[CurrentSession, Depends(resolve_session)]


async def require_admin_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_admin_key: Annotated[str | None, Header()] = None,
) -> None:
    """Guard de `/admin/*` (RF-404). Los endpoints son de la semana 7; el guard es de acá.

    Con `DS_ADMIN_KEY` vacío rechaza todo: un despliegue al que se le olvidó configurar la clave
    tiene que quedar cerrado, no abierto.
    """
    if not settings.admin_key or x_admin_key != settings.admin_key:
        raise ApiError(
            "admin_key_required",
            "a valid X-Admin-Key header is required",
            status.HTTP_401_UNAUTHORIZED,
        )
