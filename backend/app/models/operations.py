"""Operación: parámetros del sistema y registro de auditoría del panel.

Las dos tablas existen por la misma razón —que una decisión operativa quede en datos y no en el
código— y son las dos que sostienen RF-606 y RF-405. Ver docs/11-modelo-de-datos.md §3.12 y §3.13.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow

#: Las acciones que el panel puede registrar. Ampliar esta tupla exige una migración: el CHECK
#: vive en la base para que un `action` mal escrito falle en el INSERT y no aparezca meses después
#: como una fila huérfana en la auditoría.
AUDIT_ACTIONS = (
    "activate_patch",
    "set_pool_tier",
    "set_enabled_tiers",
    "set_setting",
    "flag_respondent",
    "trigger_export",
)


class AppSetting(Base):
    """Un parámetro operativo. Ninguno es una constante del código (RF-606)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    value: Mapped[Any] = mapped_column(pg.JSONB, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=utcnow()
    )
    updated_by: Mapped[str | None] = mapped_column(sa.Text)

    __table_args__ = (
        # Sin el punto que obliga a `bloque.nombre`, la tabla degenera en un cajón de sastre.
        sa.CheckConstraint(
            r"key ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'", name="app_settings_key_format"
        ),
    )


class AdminAudit(Base):
    """Toda acción de administración deja rastro. Append-only, como `responses` (RF-405)."""

    __tablename__ = "admin_audit"

    audit_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(sa.Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=utcnow()
    )

    __table_args__ = (
        sa.CheckConstraint(
            "action IN ({})".format(", ".join(f"'{a}'" for a in AUDIT_ACTIONS)),
            name="admin_audit_action_valid",
        ),
        sa.Index("admin_audit_recent", sa.text("created_at DESC")),
    )
