"""Completar el esquema con lo que `docs/11-modelo-de-datos.md` ya especificaba.

La migración 0001 dejó afuera dos tablas (`app_settings` §3.12 y `admin_audit` §3.13), cinco
columnas (las cuatro de la racha de días en `respondents` §3.7 y `coverage_deficit` en `questions`
§3.8), un índice (`responses_recent` §3.9) y una cláusula del CHECK
`respondents_counters_consistent`.

El desvío pasó inadvertido porque `infra/check_docs.py` valida el DDL del documento y
`tests/test_schema.py` comparaba la migración contra los modelos: nadie comparaba el documento
contra los modelos. Esta migración cierra el desvío y `test_models_match_documented_ddl` impide
que se repita.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- respondents: la racha de días (docs/23-gamificacion.md §2.2) ---------------------------
    op.add_column(
        "respondents",
        sa.Column("answers_today", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("respondents", sa.Column("last_active_date", sa.Date(), nullable=True))
    op.add_column(
        "respondents",
        sa.Column("current_day_streak", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "respondents",
        sa.Column("best_day_streak", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )

    # El CHECK se reemplaza entero: Postgres no permite agregarle una cláusula a uno existente.
    op.drop_constraint("respondents_counters_consistent", "respondents", type_="check")
    op.create_check_constraint(
        "respondents_counters_consistent",
        "respondents",
        "honeypot_passed <= honeypot_attempts "
        "AND retest_consistent <= retest_pairs "
        "AND current_streak <= best_streak "
        "AND current_day_streak <= best_day_streak",
    )

    # --- questions: el tercer término de la prioridad del sampler (docs/21-sampler.md §3.3) -----
    op.add_column("questions", sa.Column("coverage_deficit", sa.Numeric(5, 4), nullable=True))
    op.create_check_constraint(
        "questions_coverage_range",
        "questions",
        "coverage_deficit IS NULL OR coverage_deficit BETWEEN 0 AND 1",
    )

    # --- responses: ventanas de día y semana del leaderboard (docs/23-gamificacion.md §5.3) -----
    # En crudo porque Alembic no expresa el orden DESC de una columna de índice.
    op.execute("CREATE INDEX responses_recent ON responses (created_at DESC)")

    # --- app_settings: los parámetros operativos (RF-606) ---------------------------------------
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", pg.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.CheckConstraint(
            r"key ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'", name="app_settings_key_format"
        ),
        sa.PrimaryKeyConstraint("key", name="pk_app_settings"),
    )

    # --- admin_audit: el registro append-only del panel (RF-405) --------------------------------
    op.create_table(
        "admin_audit",
        sa.Column("audit_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            pg.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('activate_patch', 'set_pool_tier', 'set_enabled_tiers', "
            "'set_setting', 'flag_respondent', 'trigger_export')",
            name="admin_audit_action_valid",
        ),
        sa.PrimaryKeyConstraint("audit_id", name="pk_admin_audit"),
    )
    op.execute("CREATE INDEX admin_audit_recent ON admin_audit (created_at DESC)")


def downgrade() -> None:
    op.drop_table("admin_audit")
    op.drop_table("app_settings")

    op.execute("DROP INDEX IF EXISTS responses_recent")

    op.drop_constraint("questions_coverage_range", "questions", type_="check")
    op.drop_column("questions", "coverage_deficit")

    op.drop_constraint("respondents_counters_consistent", "respondents", type_="check")
    op.drop_column("respondents", "best_day_streak")
    op.drop_column("respondents", "current_day_streak")
    op.drop_column("respondents", "last_active_date")
    op.drop_column("respondents", "answers_today")
    op.create_check_constraint(
        "respondents_counters_consistent",
        "respondents",
        "honeypot_passed <= honeypot_attempts "
        "AND retest_consistent <= retest_pairs "
        "AND current_streak <= best_streak",
    )
