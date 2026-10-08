"""El estado que necesitan las honeypots y los retests (ADR-020).

Cuatro columnas nulables en `respondents` (`docs/11-modelo-de-datos.md` §3.7):

- `next_honeypot_at` y `next_retest_at`, la posición a partir de la cual toca cada cadencia
  (`docs/22-calidad-de-datos.md` §3.6 y §4);
- `pending_honeypot`, la honeypot servida y todavía no contestada. Sin ella, la precarga del
  cliente —que pide el lote siguiente con tarjetas en cola— producía honeypots dobles;
- `pending_retest_of`, la respuesta original que el sampler sirvió como retest y todavía no se
  contestó. Es lo que permite escribir `is_retest_of` sin que el cliente sepa cuál es el retest.

Son nulables a propósito: `NULL` quiere decir «ventana todavía no abierta» o «nada pendiente», y
el sampler abre las ventanas en el primer lote. Así los respondedores que ya existían no necesitan
un valor inventado acá.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("respondents", sa.Column("next_honeypot_at", sa.Integer(), nullable=True))
    op.add_column("respondents", sa.Column("next_retest_at", sa.Integer(), nullable=True))
    op.add_column("respondents", sa.Column("pending_honeypot", sa.BigInteger(), nullable=True))
    op.add_column("respondents", sa.Column("pending_retest_of", sa.BigInteger(), nullable=True))
    # Los nombres son los del DDL documentado, no los de la convención: `respondents` y las tablas
    # a las que apuntan se referencian en los dos sentidos, y el documento declara estas FK aparte,
    # con nombre propio.
    op.create_foreign_key(
        "respondents_pending_honeypot_fk",
        "respondents",
        "questions",
        ["pending_honeypot"],
        ["question_id"],
    )
    op.create_foreign_key(
        "respondents_pending_retest_fk",
        "respondents",
        "responses",
        ["pending_retest_of"],
        ["response_id"],
    )


def downgrade() -> None:
    op.drop_constraint("respondents_pending_retest_fk", "respondents", type_="foreignkey")
    # `IF EXISTS` sólo en `pending_honeypot`: la primera versión de esta migración, que llegó a
    # staging el 16/09, no la tenía (se agregó el 17/09, ADR-020). Sin esto, esa base no podría
    # bajar a 0002 para volver a subir con la versión completa.
    op.execute(
        "ALTER TABLE respondents DROP CONSTRAINT IF EXISTS respondents_pending_honeypot_fk"
    )
    op.drop_column("respondents", "pending_retest_of")
    op.execute("ALTER TABLE respondents DROP COLUMN IF EXISTS pending_honeypot")
    op.drop_column("respondents", "next_retest_at")
    op.drop_column("respondents", "next_honeypot_at")
