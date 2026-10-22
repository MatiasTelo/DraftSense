"""Escribir y leer `admin_audit` (RF-405, `docs/24-panel-admin.md` §4 y §3.10).

`record` no hace commit: la fila tiene que entrar en la misma transacción que el cambio que
registra, o una caída entre los dos dejaría un cambio sin rastro o un rastro sin cambio.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import uuid
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AUDIT_ACTIONS, AdminAudit

PAGE_SIZE: Final = 50


def plain(value: Any) -> Any:
    """Un valor apto para `jsonb`: los resultados de los services traen dataclasses, `Decimal`,
    fechas y enums, que `json` no sabe serializar."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [plain(v) for v in value]
    if isinstance(value, set | frozenset):
        return [plain(v) for v in sorted(value)]
    if isinstance(value, enum.Enum):
        return plain(value.value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dt.date | dt.datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def record(session: AsyncSession, action: str, payload: Mapping[str, Any]) -> None:
    """Agrega la fila a la sesión. **No hace commit.**"""
    if action not in AUDIT_ACTIONS:
        # El CHECK de la base lo rechazaría igual, pero recién en el commit y con un error que no
        # dice qué acción era.
        raise ValueError(f"acción de auditoría desconocida: {action}")
    session.add(AdminAudit(action=action, payload=plain(payload)))


async def page(
    session: AsyncSession, number: int = 1, action: str | None = None
) -> dict[str, Any]:
    """Una página de la auditoría, de la más nueva a la más vieja."""
    number = max(number, 1)
    conditions = [AdminAudit.action == action] if action else []
    total = (
        await session.execute(sa.select(sa.func.count()).select_from(AdminAudit).where(*conditions))
    ).scalar_one()
    rows = (
        await session.execute(
            sa.select(AdminAudit)
            .where(*conditions)
            .order_by(AdminAudit.created_at.desc(), AdminAudit.audit_id.desc())
            .offset((number - 1) * PAGE_SIZE)
            .limit(PAGE_SIZE)
        )
    ).scalars()
    return {
        "items": [
            {
                "audit_id": row.audit_id,
                "action": row.action,
                "payload": row.payload,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "page": number,
        "page_size": PAGE_SIZE,
        "total": total,
        "actions": list(AUDIT_ACTIONS),
    }


async def last_by_job(session: AsyncSession) -> dict[str, dt.datetime]:
    """La última corrida auditada de cada job: sobrevive a un reinicio del proceso, el estado en
    memoria no."""
    job = AdminAudit.payload["job"].astext
    rows = await session.execute(
        sa.select(job, sa.func.max(AdminAudit.created_at))
        .where(AdminAudit.action == "run_job")
        .group_by(job)
    )
    return {name: when for name, when in rows.tuples() if name is not None}
