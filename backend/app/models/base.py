"""Declarative base y convenciones de nombres."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase

#: Nombres deterministas para índices y restricciones.
#: Sin esto, Alembic genera nombres distintos en cada corrida y los `downgrade()` no encuentran
#: qué borrar.
#:
#: Los `CHECK` usan el nombre tal cual se declara, sin prefijo: en este esquema todos se nombran
#: a mano y ya llevan el nombre de la tabla (`questions_shape`, `responses_answer_shape`), de modo
#: que los nombres reales en Postgres coinciden literalmente con los del DDL documentado en
#: `docs/11-modelo-de-datos.md`.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> sa.TextClause:
    """`now()` de Postgres, para defaults del lado del servidor."""
    return sa.text("now()")
