"""Vistas de sólo lectura: resumen, conectividad, cobertura, calidad y auditoría (24 §3)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from draftsense_admin.dependencies import SessionDep, domain_errors
from draftsense_admin.services import audit, stats

router = APIRouter(tags=["monitoreo"])


@router.get("/overview")
async def overview(session: SessionDep, days: int = Query(30)) -> dict[str, Any]:
    with domain_errors():
        return await stats.overview(session, days=days)


@router.get("/connectivity")
async def connectivity(session: SessionDep) -> dict[str, Any]:
    return await stats.connectivity_report(session)


@router.get("/coverage")
async def coverage(session: SessionDep) -> dict[str, Any]:
    return await stats.coverage(session)


@router.get("/quality")
async def quality(session: SessionDep) -> dict[str, Any]:
    return await stats.quality(session)


@router.get("/audit")
async def audit_log(
    session: SessionDep, page: int = Query(1, ge=1), action: str | None = None
) -> dict[str, Any]:
    return await audit.page(session, page, action or None)
