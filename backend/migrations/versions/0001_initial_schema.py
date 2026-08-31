"""Esquema inicial de DraftSense.

Crea los cinco tipos ENUM, las once tablas y sus índices, tal como los especifica
`docs/11-modelo-de-datos.md`.

Revision ID: 0001
Revises:
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Los tipos ENUM se declaran con create_type=False para que las tablas los referencien sin
# intentar crearlos de nuevo: los crea explícitamente el bloque de arriba de upgrade().
def _enum(name: str) -> pg.ENUM:
    return pg.ENUM(name=name, create_type=False)


ENUMS: dict[str, tuple[str, ...]] = {
    "question_type": (
        "pairwise_dimension",
        "peak_timing",
        "lane_matchup",
        "duo_synergy",
        "trait_multiselect",
    ),
    "aggregate_scope": (
        "champion_dimension",
        "champion_peak",
        "matchup_pair",
        "duo_synergy",
        "duo_lane_strength",
        "champion_trait",
    ),
    "support_level": ("solid", "limited", "insufficient"),
    "lane_role": ("top", "jungle", "mid", "adc", "support"),
    "duo_context": ("bot", "top_jungle", "mid_jungle"),
}


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    for name, values in ENUMS.items():
        rendered = ", ".join(f"'{v}'" for v in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({rendered})")

    # ---------------------------------------------------------------- catálogo

    op.create_table(
        "patches",
        sa.Column("patch_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("released_at", sa.Date(), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.CheckConstraint(r"version ~ '^\d+\.\d+$'", name="patches_version_format"),
        sa.PrimaryKeyConstraint("patch_id", name="pk_patches"),
        sa.UniqueConstraint("version", name="uq_patches_version"),
    )
    op.execute(
        "CREATE UNIQUE INDEX patches_single_current ON patches (is_current) WHERE is_current"
    )

    op.create_table(
        "champions",
        sa.Column("champion_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("riot_key", sa.Text(), nullable=False),
        sa.Column("riot_name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "roles", pg.ARRAY(_enum("lane_role")), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("patch_first_seen", sa.Integer(), nullable=False),
        sa.Column("pool_tier", sa.SmallInteger(), server_default=sa.text("3"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("pool_tier BETWEEN 1 AND 3", name="champions_pool_tier_range"),
        sa.CheckConstraint("cardinality(roles) > 0", name="champions_has_roles"),
        sa.ForeignKeyConstraint(
            ["patch_first_seen"], ["patches.patch_id"], name="fk_champions_patch_first_seen"
        ),
        sa.PrimaryKeyConstraint("champion_id", name="pk_champions"),
        sa.UniqueConstraint("riot_key", name="uq_champions_riot_key"),
    )
    op.execute("CREATE INDEX champions_active_pool ON champions (pool_tier) WHERE is_active")
    op.execute("CREATE INDEX champions_roles_gin ON champions USING gin (roles)")

    op.create_table(
        "dimensions",
        sa.Column("dimension_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("label_en", sa.Text(), nullable=False),
        sa.Column("label_es", sa.Text(), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=False),
        sa.Column("description_es", sa.Text(), nullable=True),
        sa.Column("prompt_en", sa.Text(), nullable=False),
        sa.Column("prompt_es", sa.Text(), nullable=True),
        sa.Column("display_order", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint(r"code ~ '^[a-z][a-z0-9_]{1,30}$'", name="dimensions_code_format"),
        sa.PrimaryKeyConstraint("dimension_id", name="pk_dimensions"),
        sa.UniqueConstraint("code", name="uq_dimensions_code"),
    )

    op.create_table(
        "traits",
        sa.Column("trait_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("label_en", sa.Text(), nullable=False),
        sa.Column("label_es", sa.Text(), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=False),
        sa.Column("description_es", sa.Text(), nullable=True),
        sa.Column("legacy_tag", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("display_order", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint(r"code ~ '^[a-z][a-z0-9_]{1,30}$'", name="traits_code_format"),
        sa.PrimaryKeyConstraint("trait_id", name="pk_traits"),
        sa.UniqueConstraint("code", name="uq_traits_code"),
    )

    op.create_table(
        "pick_rate_snapshots",
        sa.Column("snapshot_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.Date(), nullable=False),
        sa.Column("patch_id", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["patch_id"], ["patches.patch_id"], name="fk_pick_rate_snapshots_patch_id"
        ),
        sa.PrimaryKeyConstraint("snapshot_id", name="pk_pick_rate_snapshots"),
        sa.UniqueConstraint(
            "source", "patch_id", "captured_at", name="pick_rate_snapshots_unique"
        ),
    )

    op.create_table(
        "pick_rate_entries",
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("champion_id", sa.Integer(), nullable=False),
        sa.Column("role", _enum("lane_role"), nullable=False),
        sa.Column("pick_rate", sa.Numeric(6, 4), nullable=False),
        sa.Column("rank_in_role", sa.Integer(), nullable=False),
        sa.CheckConstraint("pick_rate >= 0 AND pick_rate <= 1", name="pick_rate_range"),
        sa.ForeignKeyConstraint(
            ["champion_id"], ["champions.champion_id"], name="fk_pick_rate_entries_champion_id"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["pick_rate_snapshots.snapshot_id"],
            name="fk_pick_rate_entries_snapshot_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "snapshot_id", "champion_id", "role", name="pk_pick_rate_entries"
        ),
    )

    # ------------------------------------------------------------- recolección

    op.create_table(
        "respondents",
        sa.Column(
            "respondent_id",
            pg.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("session_token_hash", sa.Text(), nullable=False),
        sa.Column("fingerprint_hash", sa.Text(), nullable=False),
        sa.Column("declared_rank", sa.Text(), nullable=True),
        sa.Column("declared_main_role", _enum("lane_role"), nullable=True),
        sa.Column("declared_hours_bucket", sa.Text(), nullable=True),
        sa.Column("onboarding_seen", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "trust_score", sa.Numeric(4, 3), server_default=sa.text("0.500"), nullable=False
        ),
        sa.Column("honeypot_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("honeypot_passed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("retest_pairs", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("retest_consistent", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("fast_answers", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("straightline_runs", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("answers_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("current_streak", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("best_streak", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("alias", sa.Text(), nullable=True),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_flagged", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.CheckConstraint("trust_score BETWEEN 0 AND 1", name="respondents_trust_range"),
        sa.CheckConstraint(
            "declared_rank IS NULL OR declared_rank IN ('iron', 'bronze', 'silver', 'gold', "
            "'platinum', 'emerald', 'diamond', 'master', 'grandmaster', 'challenger', "
            "'unranked')",
            name="respondents_rank_valid",
        ),
        sa.CheckConstraint(
            "declared_hours_bucket IS NULL OR declared_hours_bucket IN "
            "('<5', '5-15', '15-30', '30+')",
            name="respondents_hours_valid",
        ),
        sa.CheckConstraint(
            "honeypot_passed <= honeypot_attempts AND retest_consistent <= retest_pairs "
            "AND current_streak <= best_streak",
            name="respondents_counters_consistent",
        ),
        sa.PrimaryKeyConstraint("respondent_id", name="pk_respondents"),
        sa.UniqueConstraint("session_token_hash", name="uq_respondents_session_token_hash"),
    )
    op.execute("CREATE INDEX respondents_fingerprint ON respondents (fingerprint_hash)")
    op.execute(
        "CREATE INDEX respondents_leaderboard ON respondents (answers_count DESC) "
        "WHERE NOT is_flagged"
    )

    op.create_table(
        "questions",
        sa.Column("question_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("type", _enum("question_type"), nullable=False),
        sa.Column("champion_a", sa.Integer(), nullable=False),
        sa.Column("champion_b", sa.Integer(), nullable=True),
        sa.Column("champion_c", sa.Integer(), nullable=True),
        sa.Column("champion_d", sa.Integer(), nullable=True),
        sa.Column("dimension_id", sa.Integer(), nullable=True),
        sa.Column("role", _enum("lane_role"), nullable=True),
        sa.Column("duo_ctx", _enum("duo_context"), nullable=True),
        sa.Column("patch_id", sa.Integer(), nullable=False),
        sa.Column("is_honeypot", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("expected_answer", pg.JSONB(), nullable=True),
        sa.Column("exposure_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "answer_counts",
            pg.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("entropy", sa.Numeric(5, 4), nullable=True),
        sa.Column("bridge_priority", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("stats_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["champion_a"], ["champions.champion_id"], name="fk_questions_champion_a"
        ),
        sa.ForeignKeyConstraint(
            ["champion_b"], ["champions.champion_id"], name="fk_questions_champion_b"
        ),
        sa.ForeignKeyConstraint(
            ["champion_c"], ["champions.champion_id"], name="fk_questions_champion_c"
        ),
        sa.ForeignKeyConstraint(
            ["champion_d"], ["champions.champion_id"], name="fk_questions_champion_d"
        ),
        sa.ForeignKeyConstraint(
            ["dimension_id"], ["dimensions.dimension_id"], name="fk_questions_dimension_id"
        ),
        sa.ForeignKeyConstraint(["patch_id"], ["patches.patch_id"], name="fk_questions_patch_id"),
        sa.PrimaryKeyConstraint("question_id", name="pk_questions"),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX questions_identity ON questions (
            type, patch_id, champion_a, champion_b, champion_c, champion_d,
            dimension_id, role, duo_ctx
        ) NULLS NOT DISTINCT
        """
    )
    op.execute(
        "CREATE INDEX questions_sampler ON questions (type, patch_id, exposure_count) "
        "WHERE NOT is_honeypot"
    )
    op.execute("CREATE INDEX questions_honeypots ON questions (patch_id) WHERE is_honeypot")
    op.execute(
        "CREATE INDEX questions_bridges ON questions (patch_id, dimension_id) "
        "WHERE bridge_priority"
    )

    op.create_table(
        "responses",
        sa.Column("response_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("respondent_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", sa.BigInteger(), nullable=False),
        sa.Column("type", _enum("question_type"), nullable=False),
        sa.Column("patch_id", sa.Integer(), nullable=False),
        sa.Column("answer", pg.JSONB(), nullable=False),
        sa.Column("response_time_ms", sa.Integer(), nullable=False),
        sa.Column("is_retest_of", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "response_time_ms >= 0 AND response_time_ms < 600000", name="responses_time_sane"
        ),
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
        sa.ForeignKeyConstraint(
            ["is_retest_of"], ["responses.response_id"], name="fk_responses_is_retest_of"
        ),
        sa.ForeignKeyConstraint(["patch_id"], ["patches.patch_id"], name="fk_responses_patch_id"),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.question_id"], name="fk_responses_question_id"
        ),
        sa.ForeignKeyConstraint(
            ["respondent_id"], ["respondents.respondent_id"], name="fk_responses_respondent_id"
        ),
        sa.PrimaryKeyConstraint("response_id", name="pk_responses"),
    )
    op.execute(
        "CREATE UNIQUE INDEX responses_one_per_question ON responses "
        "(respondent_id, question_id) WHERE is_retest_of IS NULL"
    )
    op.execute("CREATE INDEX responses_by_question ON responses (question_id, created_at)")
    op.execute(
        "CREATE INDEX responses_by_respondent ON responses (respondent_id, created_at DESC)"
    )
    op.execute("CREATE INDEX responses_by_patch_type ON responses (patch_id, type)")

    # ----------------------------------------------------------------- salidas

    op.create_table(
        "aggregates",
        sa.Column("aggregate_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("scope", _enum("aggregate_scope"), nullable=False),
        sa.Column("champion_id", sa.Integer(), nullable=False),
        sa.Column("champion_b_id", sa.Integer(), nullable=True),
        sa.Column("dimension_id", sa.Integer(), nullable=True),
        sa.Column("trait_id", sa.Integer(), nullable=True),
        sa.Column("role", _enum("lane_role"), nullable=True),
        sa.Column("duo_ctx", _enum("duo_context"), nullable=True),
        sa.Column("patch_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Numeric(9, 5), nullable=False),
        sa.Column("ci_low", sa.Numeric(9, 5), nullable=True),
        sa.Column("ci_high", sa.Numeric(9, 5), nullable=True),
        sa.Column("n_responses", sa.Integer(), nullable=False),
        sa.Column("n_comparisons", sa.Integer(), nullable=True),
        sa.Column("support", _enum("support_level"), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("patch_window", sa.Text(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "champion_b_id IS NULL OR champion_id < champion_b_id",
            name="aggregates_canonical_pair",
        ),
        sa.ForeignKeyConstraint(
            ["champion_b_id"], ["champions.champion_id"], name="fk_aggregates_champion_b_id"
        ),
        sa.ForeignKeyConstraint(
            ["champion_id"], ["champions.champion_id"], name="fk_aggregates_champion_id"
        ),
        sa.ForeignKeyConstraint(
            ["dimension_id"], ["dimensions.dimension_id"], name="fk_aggregates_dimension_id"
        ),
        sa.ForeignKeyConstraint(
            ["patch_id"], ["patches.patch_id"], name="fk_aggregates_patch_id"
        ),
        sa.ForeignKeyConstraint(
            ["trait_id"], ["traits.trait_id"], name="fk_aggregates_trait_id"
        ),
        sa.PrimaryKeyConstraint("aggregate_id", name="pk_aggregates"),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX aggregates_identity ON aggregates (
            scope, champion_id, champion_b_id, dimension_id, trait_id,
            role, duo_ctx, patch_id
        ) NULLS NOT DISTINCT
        """
    )

    op.create_table(
        "exports",
        sa.Column("export_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("patch_id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_kind", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("responses_included", sa.Integer(), nullable=False),
        sa.Column("respondents_included", sa.Integer(), nullable=False),
        sa.Column("min_trust_applied", sa.Numeric(4, 3), nullable=False),
        sa.Column("patch_window", sa.Text(), nullable=False),
        sa.Column("decay_halflife_days", sa.Numeric(6, 2), nullable=True),
        sa.Column("bootstrap_samples", sa.Integer(), nullable=True),
        sa.Column("aggregation_version", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "file_kind IN ('champion_features', 'matchup_matrix', 'duo_features', "
            "'quality_report')",
            name="exports_kind_valid",
        ),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="exports_sha256_format"),
        sa.ForeignKeyConstraint(["patch_id"], ["patches.patch_id"], name="fk_exports_patch_id"),
        sa.PrimaryKeyConstraint("export_id", name="pk_exports"),
    )
    op.execute("CREATE INDEX exports_by_patch ON exports (patch_id, created_at DESC)")


def downgrade() -> None:
    for table in (
        "exports",
        "aggregates",
        "responses",
        "questions",
        "respondents",
        "pick_rate_entries",
        "pick_rate_snapshots",
        "traits",
        "dimensions",
        "champions",
        "patches",
    ):
        op.drop_table(table)

    for name in reversed(list(ENUMS)):
        op.execute(f"DROP TYPE IF EXISTS {name}")
