"""Sesión e identidad — CA-001 a CA-005 de `docs/03-criterios-aceptacion.md` §1."""

from __future__ import annotations

import re

import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LaneRole, Respondent
from app.services import sessions
from tests.conftest import as_respondent, requires_db

HEX64 = re.compile(r"^[0-9a-f]{64}$")


@requires_db
async def test_crear_sesion_anonima(client: AsyncClient, db: AsyncSession) -> None:
    """CA-001 — 201, cookie con los cuatro atributos, y trust score 0.500."""
    response = await client.post("/sessions", headers={"X-Client-Fingerprint": "abc"})
    assert response.status_code == 201

    body = response.json()
    assert body["answers_count"] == 0
    assert body["onboarding_seen"] is False
    assert body["current_day_streak"] == 0

    raw = response.headers["set-cookie"]
    assert "ds_session=" in raw
    assert "HttpOnly" in raw
    assert "Secure" in raw
    assert "SameSite=lax" in raw.replace("SameSite=Lax", "SameSite=lax")
    assert "Max-Age=15552000" in raw

    row = (
        await db.execute(
            sa.select(Respondent).where(Respondent.respondent_id == body["respondent_id"])
        )
    ).scalar_one()
    assert float(row.trust_score) == 0.500


@requires_db
async def test_la_creacion_es_idempotente(
    client: AsyncClient, respondent: tuple[Respondent, str]
) -> None:
    """CA-002 — con cookie válida no se crea una identidad nueva."""
    row, token = respondent
    before = row.last_seen

    response = await as_respondent(client, token).post("/sessions")

    assert response.status_code == 200
    assert response.json()["respondent_id"] == str(row.respondent_id)
    assert row.last_seen > before


@requires_db
async def test_el_token_no_se_guarda_en_claro(
    client: AsyncClient, db: AsyncSession
) -> None:
    """CA-003 — en la base vive el SHA-256, nunca el valor de la cookie."""
    response = await client.post("/sessions")
    token = response.cookies["ds_session"]

    row = (
        await db.execute(
            sa.select(Respondent).where(
                Respondent.respondent_id == response.json()["respondent_id"]
            )
        )
    ).scalar_one()

    assert HEX64.match(row.session_token_hash)
    assert row.session_token_hash != token
    assert row.session_token_hash == sessions.hash_token(token)


@requires_db
async def test_omitir_el_onboarding_es_una_respuesta(
    client: AsyncClient, respondent: tuple[Respondent, str]
) -> None:
    """CA-005 — los tres nulos marcan `onboarding_seen` igual."""
    row, token = respondent
    response = await as_respondent(client, token).post(
        "/sessions/onboarding",
        json={
            "declared_rank": None,
            "declared_main_role": None,
            "declared_hours_bucket": None,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"onboarding_seen": True}
    assert row.onboarding_seen is True
    assert row.declared_rank is None


@requires_db
async def test_onboarding_guarda_los_tres_campos(
    client: AsyncClient, respondent: tuple[Respondent, str]
) -> None:
    """RF-005 — el camino feliz del onboarding."""
    row, token = respondent
    response = await as_respondent(client, token).post(
        "/sessions/onboarding",
        json={
            "declared_rank": "platinum",
            "declared_main_role": "support",
            "declared_hours_bucket": "5-15",
        },
    )

    assert response.status_code == 200
    assert row.declared_rank == "platinum"
    assert row.declared_main_role is LaneRole.SUPPORT
    assert row.declared_hours_bucket == "5-15"


@requires_db
async def test_onboarding_rechaza_un_rango_inventado(
    client: AsyncClient, respondent: tuple[Respondent, str]
) -> None:
    """El CHECK de la tabla no debe ser la primera línea de defensa: 400, no 500."""
    _, token = respondent
    response = await as_respondent(client, token).post(
        "/sessions/onboarding", json={"declared_rank": "radiant"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_parameter"


@requires_db
async def test_endpoint_sin_cookie_crea_la_sesion(client: AsyncClient) -> None:
    """`docs/12-api.md` §1.3 — no tener sesión no es un error, es el estado inicial."""
    response = await client.get("/me")

    assert response.status_code == 200
    assert "ds_session=" in response.headers["set-cookie"]
    assert response.json()["answers_count"] == 0
