"""El hash con sal de la IP de creación, para el límite de tasa por IP (ADR-033).

Una columna nulable en `respondents` (`docs/11-modelo-de-datos.md` §3.7): `ip_hash`, el
HMAC-SHA-256 de la IP con la que se creó el respondedor. La sal vive sólo en el entorno
(`DS_IP_HASH_SALT`) y la IP en claro sigue sin guardarse.

Es nulable a propósito: los respondedores anteriores a esta migración no tienen de dónde sacarla,
y sin sal configurada la aplicación no guarda nada. `NULL` quiere decir «a este respondedor sólo lo
alcanza el límite por respondedor» (RF-209, `docs/12-api.md` §4).

El índice es parcial por lo mismo: sólo se consulta por un `ip_hash` concreto.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("respondents", sa.Column("ip_hash", sa.Text(), nullable=True))
    op.create_index(
        "respondents_ip_hash",
        "respondents",
        ["ip_hash"],
        postgresql_where=sa.text("ip_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("respondents_ip_hash", table_name="respondents")
    op.drop_column("respondents", "ip_hash")
