"""Recolección: respondedores, preguntas y respuestas.

`responses` es la tabla irremplazable del proyecto: append-only, con la validación de forma
expresada como restricción de tabla. Ver ADR-002.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow
from app.models.enums import (
    DUO_CONTEXT,
    LANE_ROLE,
    QUESTION_TYPE,
    DuoContext,
    LaneRole,
    QuestionType,
)

VALID_RANKS = (
    "iron",
    "bronze",
    "silver",
    "gold",
    "platinum",
    "emerald",
    "diamond",
    "master",
    "grandmaster",
    "challenger",
    "unranked",
)
VALID_HOURS_BUCKETS = ("<5", "5-15", "15-30", "30+")


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class Respondent(Base):
    """Una identidad anónima. Sin login, sin datos personales (ADR-001)."""

    __tablename__ = "respondents"

    respondent_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    session_token_hash: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    fingerprint_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)

    # Onboarding. Los tres opcionales: NULL = prefirió no decir u omitió.
    declared_rank: Mapped[str | None] = mapped_column(sa.Text)
    declared_main_role: Mapped[LaneRole | None] = mapped_column(LANE_ROLE)
    declared_hours_bucket: Mapped[str | None] = mapped_column(sa.Text)
    onboarding_seen: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )

    # Calidad. Derivados, nunca ingresados.
    trust_score: Mapped[Decimal] = mapped_column(
        sa.Numeric(4, 3), nullable=False, server_default=sa.text("0.500")
    )
    honeypot_attempts: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    honeypot_passed: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    retest_pairs: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    retest_consistent: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    fast_answers: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    straightline_runs: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )

    # Gamificación.
    answers_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    current_streak: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    best_streak: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    alias: Mapped[str | None] = mapped_column(sa.Text)

    first_seen: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=utcnow()
    )
    last_seen: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=utcnow()
    )
    is_flagged: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )

    __table_args__ = (
        sa.CheckConstraint("trust_score BETWEEN 0 AND 1", name="respondents_trust_range"),
        sa.CheckConstraint(
            f"declared_rank IS NULL OR declared_rank IN ({_sql_list(VALID_RANKS)})",
            name="respondents_rank_valid",
        ),
        sa.CheckConstraint(
            "declared_hours_bucket IS NULL OR declared_hours_bucket IN "
            f"({_sql_list(VALID_HOURS_BUCKETS)})",
            name="respondents_hours_valid",
        ),
        sa.CheckConstraint(
            "honeypot_passed <= honeypot_attempts "
            "AND retest_consistent <= retest_pairs "
            "AND current_streak <= best_streak",
            name="respondents_counters_consistent",
        ),
        sa.Index("respondents_fingerprint", "fingerprint_hash"),
        sa.Index(
            "respondents_leaderboard",
            sa.text("answers_count DESC"),
            postgresql_where=sa.text("NOT is_flagged"),
        ),
    )


class Question(Base):
    """Una pregunta concreta —un par o una combinación específica—, no una plantilla.

    Se generan bajo demanda desde el sampler sobre los tiers de pool habilitados; el producto
    cartesiano nunca se precomputa.
    """

    __tablename__ = "questions"

    question_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[QuestionType] = mapped_column(QUESTION_TYPE, nullable=False)

    champion_a: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("champions.champion_id"), nullable=False
    )
    champion_b: Mapped[int | None] = mapped_column(
        sa.Integer, sa.ForeignKey("champions.champion_id")
    )
    champion_c: Mapped[int | None] = mapped_column(
        sa.Integer, sa.ForeignKey("champions.champion_id")
    )
    champion_d: Mapped[int | None] = mapped_column(
        sa.Integer, sa.ForeignKey("champions.champion_id")
    )

    dimension_id: Mapped[int | None] = mapped_column(
        sa.Integer, sa.ForeignKey("dimensions.dimension_id")
    )
    #: Variantes 1v1: quién ocupa ese rol.
    role: Mapped[LaneRole | None] = mapped_column(LANE_ROLE)
    #: Variantes de dupla: dónde actúan juntos.
    duo_ctx: Mapped[DuoContext | None] = mapped_column(DUO_CONTEXT)
    patch_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("patches.patch_id"), nullable=False
    )

    is_honeypot: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    expected_answer: Mapped[dict[str, Any] | None] = mapped_column(pg.JSONB)

    # Denormalizados, mantenidos por refresh_question_stats cada 15 minutos.
    exposure_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    answer_counts: Mapped[dict[str, Any]] = mapped_column(
        pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    entropy: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 4))
    #: La marca el job de conectividad: uniría dos componentes desconectadas del grafo (ADR-008).
    bridge_priority: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    stats_refreshed_at: Mapped[dt.datetime | None] = mapped_column(sa.DateTime(timezone=True))

    created_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=utcnow()
    )

    __table_args__ = (
        # Cada tipo usa exactamente los campos que le corresponden.
        # lane_matchup tiene DOS variantes: el 1v1 de línea (top/mid/adc) y el 2v2 de bot.
        sa.CheckConstraint(
            """
            CASE type
                WHEN 'pairwise_dimension' THEN
                    champion_b IS NOT NULL AND champion_c IS NULL AND champion_d IS NULL
                    AND dimension_id IS NOT NULL AND role IS NULL AND duo_ctx IS NULL
                WHEN 'peak_timing' THEN
                    champion_b IS NULL AND champion_c IS NULL AND champion_d IS NULL
                    AND dimension_id IS NULL AND role IS NULL AND duo_ctx IS NULL
                WHEN 'lane_matchup' THEN
                    dimension_id IS NULL AND (
                        (champion_b IS NOT NULL AND champion_c IS NULL AND champion_d IS NULL
                         AND role IS NOT NULL AND role IN ('top','mid','adc')
                         AND duo_ctx IS NULL)
                        OR
                        (champion_b IS NOT NULL AND champion_c IS NOT NULL
                         AND champion_d IS NOT NULL AND role IS NULL AND duo_ctx = 'bot')
                    )
                WHEN 'duo_synergy' THEN
                    champion_b IS NOT NULL AND champion_c IS NOT NULL AND champion_d IS NOT NULL
                    AND dimension_id IS NULL AND role IS NULL AND duo_ctx IS NOT NULL
                WHEN 'trait_multiselect' THEN
                    champion_b IS NULL AND champion_c IS NULL AND champion_d IS NULL
                    AND dimension_id IS NULL AND role IS NULL AND duo_ctx IS NULL
            END
            """,
            name="questions_shape",
        ),
        # Orden canónico: (A,B) y (B,A) son la MISMA pregunta y no deben duplicarse.
        sa.CheckConstraint(
            """
            CASE
                WHEN type = 'pairwise_dimension' THEN champion_a < champion_b
                WHEN type = 'lane_matchup' AND champion_c IS NULL THEN champion_a < champion_b
                WHEN type IN ('lane_matchup','duo_synergy') THEN
                    champion_a < champion_b AND champion_c < champion_d
                    AND champion_a < champion_c
                ELSE true
            END
            """,
            name="questions_canonical_order",
        ),
        sa.CheckConstraint(
            "NOT is_honeypot OR expected_answer IS NOT NULL",
            name="questions_honeypot_has_expected",
        ),
        sa.CheckConstraint(
            "entropy IS NULL OR entropy BETWEEN 0 AND 1", name="questions_entropy_range"
        ),
        # Identidad de una pregunta: impide generar duplicados desde el sampler.
        sa.Index(
            "questions_identity",
            "type",
            "patch_id",
            "champion_a",
            sa.text("COALESCE(champion_b, 0)"),
            sa.text("COALESCE(champion_c, 0)"),
            sa.text("COALESCE(champion_d, 0)"),
            sa.text("COALESCE(dimension_id, 0)"),
            sa.text("COALESCE(role::text, '')"),
            sa.text("COALESCE(duo_ctx::text, '')"),
            unique=True,
        ),
        # Camino del sampler: filtra por tipo y parche, ordena por exposición.
        sa.Index(
            "questions_sampler",
            "type",
            "patch_id",
            "exposure_count",
            postgresql_where=sa.text("NOT is_honeypot"),
        ),
        sa.Index("questions_honeypots", "patch_id", postgresql_where=sa.text("is_honeypot")),
        sa.Index(
            "questions_bridges",
            "patch_id",
            "dimension_id",
            postgresql_where=sa.text("bridge_priority"),
        ),
    )


class Response(Base):
    """Una respuesta cruda. Append-only: nunca se modifica ni se borra.

    `type` y `patch_id` son redundantes con `questions` **a propósito**: permiten expresar la
    validación del `answer` como restricción de tabla, que de otro modo requeriría un JOIN
    imposible en un CHECK, y dejan que el pipeline recorra por parche y tipo sin tocar
    `questions`.
    """

    __tablename__ = "responses"

    response_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    respondent_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), sa.ForeignKey("respondents.respondent_id"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("questions.question_id"), nullable=False
    )
    type: Mapped[QuestionType] = mapped_column(QUESTION_TYPE, nullable=False)
    patch_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("patches.patch_id"), nullable=False
    )
    answer: Mapped[dict[str, Any]] = mapped_column(pg.JSONB, nullable=False)
    response_time_ms: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    is_retest_of: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("responses.response_id")
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=utcnow()
    )

    __table_args__ = (
        sa.CheckConstraint(
            "response_time_ms >= 0 AND response_time_ms < 600000", name="responses_time_sane"
        ),
        # Validación de forma del answer. Vive en la base porque responses es append-only:
        # un dato mal formado no se puede corregir después.
        sa.CheckConstraint(
            """
            CASE type
                WHEN 'pairwise_dimension' THEN
                    (answer ->> 'choice') IN ('a','b','unknown')
                    AND (answer - 'choice') = '{}'::jsonb
                WHEN 'peak_timing' THEN
                    jsonb_typeof(answer -> 'minute') = 'number'
                    AND (answer -> 'minute') >= '0'::jsonb
                    AND (answer -> 'minute') <= '40'::jsonb
                    AND (answer - 'minute') = '{}'::jsonb
                WHEN 'lane_matchup' THEN
                    (answer ->> 'choice')
                        IN ('a_strong','a_slight','even','b_slight','b_strong')
                    AND (answer - 'choice') = '{}'::jsonb
                WHEN 'duo_synergy' THEN
                    (answer ->> 'choice') IN ('pair_1','pair_2','similar')
                    AND (answer - 'choice') = '{}'::jsonb
                WHEN 'trait_multiselect' THEN
                    jsonb_typeof(answer -> 'traits') = 'array'
                    AND (answer - 'traits') = '{}'::jsonb
            END
            """,
            name="responses_answer_shape",
        ),
        # Un respondedor responde cada pregunta una sola vez, salvo retest deliberado.
        sa.Index(
            "responses_one_per_question",
            "respondent_id",
            "question_id",
            unique=True,
            postgresql_where=sa.text("is_retest_of IS NULL"),
        ),
        sa.Index("responses_by_question", "question_id", "created_at"),
        sa.Index("responses_by_respondent", "respondent_id", sa.text("created_at DESC")),
        sa.Index("responses_by_patch_type", "patch_id", "type"),
    )


__all__ = ["VALID_HOURS_BUCKETS", "VALID_RANKS", "Question", "Respondent", "Response"]
