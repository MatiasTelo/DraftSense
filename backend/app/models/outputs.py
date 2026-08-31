"""Salidas: agregados y exportaciones.

`aggregates` es caché materializada —truncable y reconstruible desde `responses`—.
`exports` es el registro de trazabilidad de cada archivo entregado al laboratorio.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow
from app.models.enums import (
    AGGREGATE_SCOPE,
    DUO_CONTEXT,
    LANE_ROLE,
    SUPPORT_LEVEL,
    AggregateScope,
    DuoContext,
    LaneRole,
    SupportLevel,
)

EXPORT_KINDS = ("champion_features", "matchup_matrix", "duo_features", "quality_report")


class Aggregate(Base):
    """Una estimación agregada. Caché: se puede truncar y reconstruir entera."""

    __tablename__ = "aggregates"

    aggregate_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    scope: Mapped[AggregateScope] = mapped_column(AGGREGATE_SCOPE, nullable=False)
    champion_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("champions.champion_id"), nullable=False
    )
    champion_b_id: Mapped[int | None] = mapped_column(
        sa.Integer, sa.ForeignKey("champions.champion_id")
    )
    dimension_id: Mapped[int | None] = mapped_column(
        sa.Integer, sa.ForeignKey("dimensions.dimension_id")
    )
    trait_id: Mapped[int | None] = mapped_column(sa.Integer, sa.ForeignKey("traits.trait_id"))
    role: Mapped[LaneRole | None] = mapped_column(LANE_ROLE)
    duo_ctx: Mapped[DuoContext | None] = mapped_column(DUO_CONTEXT)
    patch_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("patches.patch_id"), nullable=False
    )

    value: Mapped[Decimal] = mapped_column(sa.Numeric(9, 5), nullable=False)
    ci_low: Mapped[Decimal | None] = mapped_column(sa.Numeric(9, 5))
    ci_high: Mapped[Decimal | None] = mapped_column(sa.Numeric(9, 5))

    n_responses: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    n_comparisons: Mapped[int | None] = mapped_column(sa.Integer)
    support: Mapped[SupportLevel] = mapped_column(SUPPORT_LEVEL, nullable=False)
    method: Mapped[str] = mapped_column(sa.Text, nullable=False)

    #: Qué parches entraron en esta estimación, p. ej. '16.18..16.20'.
    patch_window: Mapped[str] = mapped_column(sa.Text, nullable=False)
    computed_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=utcnow()
    )

    __table_args__ = (
        sa.CheckConstraint(
            "ci_low IS NULL OR ci_high IS NULL OR ci_low <= ci_high",
            name="aggregates_ci_ordered",
        ),
        sa.CheckConstraint(
            """
            CASE scope
                WHEN 'champion_dimension' THEN
                    champion_b_id IS NULL AND dimension_id IS NOT NULL
                    AND trait_id IS NULL AND role IS NULL AND duo_ctx IS NULL
                WHEN 'champion_peak' THEN
                    champion_b_id IS NULL AND dimension_id IS NULL
                    AND trait_id IS NULL AND role IS NULL AND duo_ctx IS NULL
                WHEN 'matchup_pair' THEN
                    champion_b_id IS NOT NULL AND dimension_id IS NULL
                    AND trait_id IS NULL AND role IS NOT NULL AND duo_ctx IS NULL
                WHEN 'duo_synergy' THEN
                    champion_b_id IS NOT NULL AND dimension_id IS NULL
                    AND trait_id IS NULL AND role IS NULL AND duo_ctx IS NOT NULL
                WHEN 'duo_lane_strength' THEN
                    champion_b_id IS NOT NULL AND dimension_id IS NULL
                    AND trait_id IS NULL AND role IS NULL AND duo_ctx = 'bot'
                WHEN 'champion_trait' THEN
                    champion_b_id IS NULL AND dimension_id IS NULL
                    AND trait_id IS NOT NULL AND role IS NULL AND duo_ctx IS NULL
            END
            """,
            name="aggregates_scope_shape",
        ),
        # Las entidades pareadas se guardan en forma canónica.
        sa.CheckConstraint(
            "champion_b_id IS NULL OR champion_id < champion_b_id",
            name="aggregates_canonical_pair",
        ),
        sa.Index(
            "aggregates_identity",
            "scope",
            "champion_id",
            sa.text("COALESCE(champion_b_id, 0)"),
            sa.text("COALESCE(dimension_id, 0)"),
            sa.text("COALESCE(trait_id, 0)"),
            sa.text("COALESCE(role::text, '')"),
            sa.text("COALESCE(duo_ctx::text, '')"),
            "patch_id",
            unique=True,
        ),
    )


class Export(Base):
    """Trazabilidad de un archivo entregado.

    Con estos parámetros más `responses` —que es append-only— cualquier corrida se reproduce
    bit a bit (CA-408).
    """

    __tablename__ = "exports"

    export_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    patch_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("patches.patch_id"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    file_kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    sha256: Mapped[str] = mapped_column(sa.Text, nullable=False)

    row_count: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    column_count: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    responses_included: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    respondents_included: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    # Parámetros de la corrida: sin esto el CSV no es reproducible.
    min_trust_applied: Mapped[Decimal] = mapped_column(sa.Numeric(4, 3), nullable=False)
    patch_window: Mapped[str] = mapped_column(sa.Text, nullable=False)
    decay_halflife_days: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 2))
    bootstrap_samples: Mapped[int | None] = mapped_column(sa.Integer)
    aggregation_version: Mapped[str] = mapped_column(sa.Text, nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=utcnow()
    )

    __table_args__ = (
        sa.CheckConstraint(
            "file_kind IN (" + ", ".join(f"'{k}'" for k in EXPORT_KINDS) + ")",
            name="exports_kind_valid",
        ),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="exports_sha256_format"),
        sa.Index("exports_by_patch", "patch_id", sa.text("created_at DESC")),
    )


__all__ = ["EXPORT_KINDS", "Aggregate", "Export"]
