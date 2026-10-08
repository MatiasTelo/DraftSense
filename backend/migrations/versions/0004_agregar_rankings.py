"""El tipo 1 como ranking de cinco campeones y la salida en formato largo.

Correcciones de la reunión del 05/10/2026 con el tutor de la organización
(`docs/11-modelo-de-datos.md` §3.9, §3.11 y §3.14):

- tabla `rankings`: cada tarjeta de tipo 1 servida, con sus cinco campeones y el par ancla
  ([ADR-022]);
- `responses.ranking_id`: las diez filas que produce un ranking lo comparten. Es nulable porque
  las respuestas de los otros tipos, y las de tipo 1 anteriores a esta migración, no tienen ranking;
- `exports_kind_valid` con los cuatro archivos por campeón que reemplazan a `champion_features`
  ([ADR-023]). `exports` todavía no tiene filas: el pipeline es de la semana 9.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_KINDS = (
    "'champion_dimensions', 'peak_timing', 'champion_lane_strength', 'champion_traits', "
    "'matchup_matrix', 'duo_features', 'quality_report'"
)
OLD_KINDS = "'champion_features', 'matchup_matrix', 'duo_features', 'quality_report'"


def upgrade() -> None:
    op.create_table(
        "rankings",
        sa.Column("ranking_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("respondent_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("patch_id", sa.Integer(), nullable=False),
        sa.Column("dimension_id", sa.Integer(), nullable=False),
        sa.Column("anchor_question_id", sa.BigInteger(), nullable=False),
        sa.Column("champions", pg.ARRAY(sa.Integer()), nullable=False),
        sa.Column("submitted_order", pg.ARRAY(sa.Integer()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("cardinality(champions) = 5", name="rankings_five_champions"),
        sa.CheckConstraint(
            "submitted_order IS NULL OR cardinality(submitted_order) = 5",
            name="rankings_order_complete",
        ),
        sa.ForeignKeyConstraint(
            ["respondent_id"],
            ["respondents.respondent_id"],
            name="fk_rankings_respondent_id",
        ),
        sa.ForeignKeyConstraint(["patch_id"], ["patches.patch_id"], name="fk_rankings_patch_id"),
        sa.ForeignKeyConstraint(
            ["dimension_id"], ["dimensions.dimension_id"], name="fk_rankings_dimension_id"
        ),
        sa.ForeignKeyConstraint(
            ["anchor_question_id"],
            ["questions.question_id"],
            name="fk_rankings_anchor_question_id",
        ),
        sa.PrimaryKeyConstraint("ranking_id", name="pk_rankings"),
    )
    op.create_index(
        "rankings_by_respondent",
        "rankings",
        ["respondent_id", sa.text("created_at DESC")],
    )

    op.add_column("responses", sa.Column("ranking_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "responses_ranking_fk", "responses", "rankings", ["ranking_id"], ["ranking_id"]
    )
    op.create_index(
        "responses_by_ranking",
        "responses",
        ["ranking_id"],
        postgresql_where=sa.text("ranking_id IS NOT NULL"),
    )

    op.drop_constraint("exports_kind_valid", "exports", type_="check")
    op.create_check_constraint("exports_kind_valid", "exports", f"file_kind IN ({NEW_KINDS})")


def downgrade() -> None:
    op.drop_constraint("exports_kind_valid", "exports", type_="check")
    op.create_check_constraint("exports_kind_valid", "exports", f"file_kind IN ({OLD_KINDS})")

    op.drop_index("responses_by_ranking", table_name="responses")
    op.drop_constraint("responses_ranking_fk", "responses", type_="foreignkey")
    op.drop_column("responses", "ranking_id")

    op.drop_index("rankings_by_respondent", table_name="rankings")
    op.drop_table("rankings")
