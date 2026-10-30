"""Semanas 8 y 9: el rol de cada campeón en las duplas, el tipo 5 no vacío y `exports.params`.

- `questions.role_a … role_d` y el `CHECK questions_duo_roles`: una pregunta de duplas guarda qué
  rol juega cada campeón, y cada dupla tiene los dos roles de su contexto
  ([ADR-026](docs/13-adr/ADR-026-rol-explicito-en-las-duplas.md)). Los roles entran en el índice de
  identidad: la misma combinación con los roles invertidos es otra pregunta.
- `responses_answer_shape` exige al menos un atributo en el tipo 5 (ADR-027).
- `exports.params`: todos los parámetros de la corrida, incluidos los que no tenían columna
  (`docs/25-agregacion.md` §12, punto 3).

Ninguna pregunta de duplas ni respuesta de tipo 5 existía antes de la semana 8, así que el upgrade
no encuentra filas que violen los CHECK nuevos. El downgrade sí puede fallar si ya hay preguntas de
duplas: el índice viejo no distingue dos preguntas que sólo difieren en los roles.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_COLUMNS = ("role_a", "role_b", "role_c", "role_d")

DUO_ROLES_CHECK = """
CASE
    WHEN duo_ctx IS NULL THEN
        role_a IS NULL AND role_b IS NULL AND role_c IS NULL AND role_d IS NULL
    WHEN duo_ctx = 'bot' THEN
        ((role_a = 'adc' AND role_b = 'support') OR (role_a = 'support' AND role_b = 'adc'))
        AND ((role_c = 'adc' AND role_d = 'support') OR (role_c = 'support' AND role_d = 'adc'))
    WHEN duo_ctx = 'top_jungle' THEN
        ((role_a = 'top' AND role_b = 'jungle') OR (role_a = 'jungle' AND role_b = 'top'))
        AND ((role_c = 'top' AND role_d = 'jungle') OR (role_c = 'jungle' AND role_d = 'top'))
    WHEN duo_ctx = 'mid_jungle' THEN
        ((role_a = 'mid' AND role_b = 'jungle') OR (role_a = 'jungle' AND role_b = 'mid'))
        AND ((role_c = 'mid' AND role_d = 'jungle') OR (role_c = 'jungle' AND role_d = 'mid'))
    ELSE false
END
"""


def answer_shape(traits_non_empty: bool) -> str:
    traits_length = (
        "AND jsonb_array_length(answer -> 'traits') >= 1" if traits_non_empty else ""
    )
    return f"""
    CASE type
        WHEN 'pairwise_dimension' THEN
            (answer ->> 'choice') IN ('a','b','unknown')
            AND (answer - 'choice') = '{{}}'::jsonb
        WHEN 'peak_timing' THEN
            jsonb_typeof(answer -> 'minute') = 'number'
            AND (answer -> 'minute') >= '0'::jsonb
            AND (answer -> 'minute') <= '40'::jsonb
            AND (answer - 'minute') = '{{}}'::jsonb
        WHEN 'lane_matchup' THEN
            (answer ->> 'choice')
                IN ('a_strong','a_slight','even','b_slight','b_strong')
            AND (answer - 'choice') = '{{}}'::jsonb
        WHEN 'duo_synergy' THEN
            (answer ->> 'choice') IN ('pair_1','pair_2','similar')
            AND (answer - 'choice') = '{{}}'::jsonb
        WHEN 'trait_multiselect' THEN
            jsonb_typeof(answer -> 'traits') = 'array'
            {traits_length}
            AND (answer - 'traits') = '{{}}'::jsonb
    END
    """


def identity_index(with_roles: bool) -> str:
    roles = ", role_a, role_b, role_c, role_d" if with_roles else ""
    return f"""
        CREATE UNIQUE INDEX questions_identity ON questions (
            type, patch_id, champion_a, champion_b, champion_c, champion_d,
            dimension_id, role, duo_ctx{roles}
        ) NULLS NOT DISTINCT
    """


def upgrade() -> None:
    lane_role = pg.ENUM(name="lane_role", create_type=False)
    for column in ROLE_COLUMNS:
        op.add_column("questions", sa.Column(column, lane_role, nullable=True))
    op.create_check_constraint("questions_duo_roles", "questions", DUO_ROLES_CHECK)
    op.execute("DROP INDEX questions_identity")
    op.execute(identity_index(with_roles=True))

    op.drop_constraint("responses_answer_shape", "responses", type_="check")
    op.create_check_constraint("responses_answer_shape", "responses", answer_shape(True))

    op.add_column(
        "exports",
        sa.Column("params", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("exports", "params")

    op.drop_constraint("responses_answer_shape", "responses", type_="check")
    op.create_check_constraint("responses_answer_shape", "responses", answer_shape(False))

    op.execute("DROP INDEX questions_identity")
    op.execute(identity_index(with_roles=False))
    op.drop_constraint("questions_duo_roles", "questions", type_="check")
    for column in reversed(ROLE_COLUMNS):
        op.drop_column("questions", column)
