"""`GET /health` — sonda de salud. Sin autenticación (`docs/12-api.md` §2.7)."""

from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter

from app.dependencies import SessionDep
from app.schemas.profile import HealthOut
from app.services import questions

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
async def health(session: SessionDep) -> HealthOut:
    """Verifica conectividad contra la base y devuelve el parche vigente.

    El `SELECT 1` no es ceremonial: sin él la sonda daría verde con la base caída, porque leer el
    parche podría venir de una conexión ya rota que sólo falla al usarse.
    """
    await session.execute(sa.text("SELECT 1"))
    patch = await questions.current_patch(session)
    return HealthOut(status="ok", current_patch=patch.version if patch else None, db="ok")
