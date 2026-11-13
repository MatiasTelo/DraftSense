"""Dependencias de FastAPI: la identidad del respondedor.

Es la única capa que traduce entre HTTP y el dominio: de acá para adentro los services reciben un
`Respondent`, no una `Request`. La API pública no tiene administración desde ADR-025: el panel
es la app local de `admin/`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
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
) -> AsyncIterator[CurrentSession]:
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
        # nunca. Lo actualiza sólo `POST /responses`: desde el 13/11/2026 tampoco `POST /sessions`,
        # que la SPA llama en cada carga y producía exactamente eso (CA-002).
        yield CurrentSession(respondent=respondent, created=False)
        return

    ip = client_ip(request)
    fingerprint = sessions.build_fingerprint(
        x_client_fingerprint, request.headers.get("user-agent"), ip
    )
    # La fila se inserta pero no se confirma todavía (ADR-033): un pedido sin cookie que termina
    # en error —un `curl` con el cuerpo mal armado, un script sin cookie contra el rate limit—
    # dejaba un respondedor vacío por pedido. Si el endpoint confirma por su cuenta en el camino,
    # la fila se confirma con él, que es lo correcto: ese pedido está saliendo bien.
    respondent, new_token = await sessions.create(
        session,
        fingerprint,
        sessions.hash_ip(ip, get_settings().ip_hash_salt),
        commit=False,
    )
    set_session_cookie(response, new_token)
    try:
        yield CurrentSession(respondent=respondent, created=True)
    except BaseException:
        await session.rollback()
        raise
    await session.commit()


# `scope="function"` hace que lo que sigue al `yield` corra ANTES de enviar la respuesta. Con el
# alcance por defecto correría después, y el navegador podría mandar el pedido siguiente con una
# cookie que la base todavía no conoce: se le crearía un segundo respondedor.
CurrentSessionDep = Annotated[CurrentSession, Depends(resolve_session, scope="function")]

