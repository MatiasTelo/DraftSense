"""La app de administración local audita también los jobs y los seeds.

`admin_audit_action_valid` suma `run_job` y `run_seed` (`docs/24-panel-admin.md` §4,
[ADR-025]). Hasta la semana 6 los jobs y los seeds sólo se corrían por CLI y no dejaban rastro;
desde el panel, correrlos es una acción de administración como cualquier otra (RF-405).

El downgrade falla si ya hay filas con las acciones nuevas: `admin_audit` es append-only, así que
no se las borra para poder bajar.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-21
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_ACTIONS = (
    "'activate_patch', 'set_pool_tier', 'set_enabled_tiers', "
    "'set_setting', 'flag_respondent', 'trigger_export'"
)
NEW_ACTIONS = f"{OLD_ACTIONS}, 'run_job', 'run_seed'"


def upgrade() -> None:
    op.drop_constraint("admin_audit_action_valid", "admin_audit", type_="check")
    op.create_check_constraint(
        "admin_audit_action_valid", "admin_audit", f"action IN ({NEW_ACTIONS})"
    )


def downgrade() -> None:
    op.drop_constraint("admin_audit_action_valid", "admin_audit", type_="check")
    op.create_check_constraint(
        "admin_audit_action_valid", "admin_audit", f"action IN ({OLD_ACTIONS})"
    )
