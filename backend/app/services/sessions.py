"""Sesiones anónimas: creación, revalidación y onboarding.

No hay registro ni login. La identidad es una cookie `ds_session` cuyo token **sólo vive en el
navegador**: en la base se guarda su SHA-256 (ADR-001, RF-003). Es lo que hace que ni un volcado
de la base permita hacerse pasar por un respondedor.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LaneRole, Respondent
from app.services.alias import generate_alias

#: Nombre de la cookie y su vida, según `docs/12-api.md` §1.3.
COOKIE_NAME = "ds_session"
COOKIE_MAX_AGE = 15_552_000  # 180 días

#: 32 bytes de entropía: el token es la única credencial del sistema y no es recuperable.
TOKEN_BYTES = 32


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_fingerprint(
    client_fingerprint: str | None, user_agent: str | None, client_ip: str | None
) -> str:
    """SHA-256 de la huella del cliente combinada con un hash de la IP (RF-004).

    La IP **nunca se guarda en claro** ni se puede recuperar de acá: entra hasheada y el resultado
    se vuelve a hashear junto al resto. El único uso de este valor es contar cuántas identidades
    creó una misma huella en 24 h (`docs/22-calidad-de-datos.md` §6.2).

    Si el cliente no manda `X-Client-Fingerprint` —JavaScript deshabilitado, un `curl`— se cae al
    user-agent. La huella queda más pobre y agrupa más de la cuenta, que es el lado correcto del
    error: la deduplicación es una señal para el trust score, no una sanción automática.
    """
    client_part = client_fingerprint or user_agent or "unknown"
    ip_part = hashlib.sha256((client_ip or "").encode("utf-8")).hexdigest()
    return hashlib.sha256(f"{client_part}|{ip_part}".encode()).hexdigest()


async def find_by_token(session: AsyncSession, token: str | None) -> Respondent | None:
    if not token:
        return None
    return (
        await session.execute(
            sa.select(Respondent).where(Respondent.session_token_hash == hash_token(token))
        )
    ).scalar_one_or_none()


async def create(session: AsyncSession, fingerprint_hash: str) -> tuple[Respondent, str]:
    """Crea un respondedor y devuelve (fila, token en claro).

    El token en claro se devuelve **una sola vez**, para ponerlo en la cookie. No queda guardado
    en ningún lado del servidor.
    """
    token = secrets.token_urlsafe(TOKEN_BYTES)
    respondent = Respondent(
        session_token_hash=hash_token(token),
        fingerprint_hash=fingerprint_hash,
        alias=generate_alias(),
    )
    session.add(respondent)
    await session.commit()
    await session.refresh(respondent)
    return respondent, token


async def touch(session: AsyncSession, respondent: Respondent) -> None:
    """Actualiza `last_seen`. Es lo único que hace una revalidación de sesión (CA-002)."""
    respondent.last_seen = dt.datetime.now(dt.UTC)
    await session.commit()


async def save_onboarding(
    session: AsyncSession,
    respondent: Respondent,
    *,
    declared_rank: str | None,
    declared_main_role: LaneRole | None,
    declared_hours_bucket: str | None,
) -> None:
    """Guarda los datos de segmentación. Los tres nulos también son una respuesta (CA-005).

    `onboarding_seen` pasa a `true` en cualquier caso: haber tocado *Skip* es información, y sin
    esta marca se le volvería a preguntar en cada sesión.
    """
    respondent.declared_rank = declared_rank
    respondent.declared_main_role = declared_main_role
    respondent.declared_hours_bucket = declared_hours_bucket
    respondent.onboarding_seen = True
    await session.commit()
