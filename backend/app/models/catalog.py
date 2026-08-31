"""Catálogo: parches, campeones, dimensiones, atributos y snapshots de pick rate.

Todo lo que se puebla con seeds y cambia por parche, no por uso del sistema.
"""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow
from app.models.enums import LANE_ROLE, LaneRole


class Patch(Base):
    """Un parche del juego. Toda respuesta se versiona contra uno."""

    __tablename__ = "patches"

    patch_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    released_at: Mapped[dt.date] = mapped_column(sa.Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )

    __table_args__ = (
        sa.CheckConstraint(r"version ~ '^\d+\.\d+$'", name="patches_version_format"),
        # A lo sumo un parche vigente a la vez.
        sa.Index(
            "patches_single_current",
            "is_current",
            unique=True,
            postgresql_where=sa.text("is_current"),
        ),
    )


class Champion(Base):
    """Un campeón del juego, poblado desde Data Dragon."""

    __tablename__ = "champions"

    champion_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    riot_key: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    riot_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    display_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    roles: Mapped[list[LaneRole]] = mapped_column(
        pg.ARRAY(LANE_ROLE), nullable=False, server_default=sa.text("'{}'")
    )
    image_url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    patch_first_seen: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("patches.patch_id"), nullable=False
    )
    #: 1 núcleo (~40), 2 expansión (~80), 3 el resto. Promover es un UPDATE, no un deploy.
    pool_tier: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("3")
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())

    __table_args__ = (
        sa.CheckConstraint("pool_tier BETWEEN 1 AND 3", name="champions_pool_tier_range"),
        sa.CheckConstraint("cardinality(roles) > 0", name="champions_has_roles"),
        sa.Index(
            "champions_active_pool", "pool_tier", postgresql_where=sa.text("is_active")
        ),
        sa.Index("champions_roles_gin", "roles", postgresql_using="gin"),
    )


class Dimension(Base):
    """Una dimensión funcional del tipo 1.

    Agregar una dimensión es insertar una fila: no requiere despliegue ni migración (RF-603).
    """

    __tablename__ = "dimensions"

    dimension_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    label_en: Mapped[str] = mapped_column(sa.Text, nullable=False)
    label_es: Mapped[str | None] = mapped_column(sa.Text)
    description_en: Mapped[str] = mapped_column(sa.Text, nullable=False)
    description_es: Mapped[str | None] = mapped_column(sa.Text)
    #: El enunciado completo de la pregunta de tipo 1 para esta dimensión.
    #: Se almacena y no se compone desde la etiqueta porque no sigue una plantilla: `scaling`
    #: pregunta "Who scales better?", no "Who has more scaling?".
    prompt_en: Mapped[str] = mapped_column(sa.Text, nullable=False)
    prompt_es: Mapped[str | None] = mapped_column(sa.Text)
    display_order: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("0")
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())

    __table_args__ = (
        sa.CheckConstraint(
            r"code ~ '^[a-z][a-z0-9_]{1,30}$'", name="dimensions_code_format"
        ),
    )


class Trait(Base):
    """Un atributo del tipo 5.

    `legacy_tag` marca las 7 etiquetas originales del laboratorio, que son las que hacen
    comparable el modelo nuevo contra el previo.
    """

    __tablename__ = "traits"

    trait_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    label_en: Mapped[str] = mapped_column(sa.Text, nullable=False)
    label_es: Mapped[str | None] = mapped_column(sa.Text)
    description_en: Mapped[str] = mapped_column(sa.Text, nullable=False)
    description_es: Mapped[str | None] = mapped_column(sa.Text)
    legacy_tag: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    display_order: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("0")
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())

    __table_args__ = (
        sa.CheckConstraint(r"code ~ '^[a-z][a-z0-9_]{1,30}$'", name="traits_code_format"),
    )


class PickRateSnapshot(Base):
    """La evidencia detrás de `champions.pool_tier`.

    Se toma a mano una vez por parche y se versiona en `infra/seeds/`. Cero dependencia externa
    en runtime (ADR-006).
    """

    __tablename__ = "pick_rate_snapshots"

    snapshot_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source_url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    captured_at: Mapped[dt.date] = mapped_column(sa.Date, nullable=False)
    patch_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("patches.patch_id"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(sa.Text)

    __table_args__ = (
        sa.UniqueConstraint(
            "source", "patch_id", "captured_at", name="pick_rate_snapshots_unique"
        ),
    )


class PickRateEntry(Base):
    """Una fila del snapshot: la tasa de selección de un campeón en un rol."""

    __tablename__ = "pick_rate_entries"

    snapshot_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("pick_rate_snapshots.snapshot_id", ondelete="CASCADE"),
        primary_key=True,
    )
    champion_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("champions.champion_id"), primary_key=True
    )
    role: Mapped[LaneRole] = mapped_column(LANE_ROLE, primary_key=True)
    pick_rate: Mapped[float] = mapped_column(sa.Numeric(6, 4), nullable=False)
    rank_in_role: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    __table_args__ = (
        sa.CheckConstraint("pick_rate >= 0 AND pick_rate <= 1", name="pick_rate_range"),
    )


__all__ = [
    "Champion",
    "Dimension",
    "Patch",
    "PickRateEntry",
    "PickRateSnapshot",
    "Trait",
    "utcnow",
]
