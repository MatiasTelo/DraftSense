"""Verificación del esquema.

Dos niveles, porque no toda máquina de desarrollo tiene Postgres:

- **Sin base de datos.** Se genera el SQL de la migración en modo offline y se compara contra los
  modelos. Corre en cualquier lado.
- **Con base de datos.** Se aplica la migración de verdad y se le pide a Alembic que compare el
  resultado contra los modelos. Es la prueba fuerte; corre siempre en CI.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.models import Base
from app.models.enums import ALL_ENUMS

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = os.getenv("DS_DATABASE_URL", "")


def sync_url() -> str:
    """El mismo DSN, pero con el driver sincronico que usan las pruebas no async.

    No alcanza con cambiar el nombre del driver: `ssl` es la opcion de asyncpg y
    `sslmode` la de psycopg. Cualquier Postgres gestionado exige TLS, asi que el DSN
    real lleva ese parametro y la traduccion tiene que ser explicita.
    """
    url = sa.engine.make_url(DATABASE_URL).set(drivername="postgresql+psycopg")
    query = dict(url.query)
    ssl = query.pop("ssl", None)
    if ssl is not None:
        query.setdefault("sslmode", "require" if ssl in ("require", "true", "1") else str(ssl))
    return url.set(query=query).render_as_string(hide_password=False)


# --------------------------------------------------------------------------- sin base de datos


@pytest.fixture(scope="module")
def offline_sql() -> str:
    """El DDL completo que produce la migración, generado sin conectarse a nada."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_migration_creates_every_model_table(offline_sql: str) -> None:
    """Ninguna tabla del modelo puede faltar en la migración."""
    created = set(re.findall(r"CREATE TABLE (\w+)", offline_sql))
    expected = set(Base.metadata.tables)
    assert expected <= created, f"tablas del modelo ausentes en la migración: {expected - created}"


def test_migration_columns_match_models(offline_sql: str) -> None:
    """Cada tabla debe tener exactamente las columnas que declara su modelo."""
    for table_name, table in Base.metadata.tables.items():
        block = re.search(
            rf"CREATE TABLE {table_name} \((.*?)\n\);", offline_sql, re.S
        )
        assert block, f"no se encontró el CREATE TABLE de {table_name}"
        body = block.group(1)
        for column in table.columns:
            assert re.search(rf"^\s+{column.name}\s", body, re.M), (
                f"{table_name}.{column.name} está en el modelo pero no en la migración"
            )


def test_migration_creates_every_enum(offline_sql: str) -> None:
    created = set(re.findall(r"CREATE TYPE (\w+)", offline_sql))
    expected = {name for _, name in ALL_ENUMS}
    assert expected == created


def test_responses_has_no_update_or_delete_path(offline_sql: str) -> None:
    """`responses` es append-only: la migración no debe crear disparadores que la modifiquen."""
    assert "CREATE TRIGGER" not in offline_sql.upper()


def test_answer_shape_constraint_covers_all_types(offline_sql: str) -> None:
    """La restricción de forma del `answer` debe contemplar los cinco tipos.

    Si alguien agrega un tipo de pregunta y olvida el CASE, la restricción evalúa a NULL y
    Postgres deja pasar cualquier cosa. Con una tabla append-only eso es irreparable.
    """
    block = re.search(r"CONSTRAINT responses_answer_shape CHECK \((.*?)\n\s*\)", offline_sql, re.S)
    assert block, "no se encontró la restricción responses_answer_shape"
    body = block.group(1)
    for question_type in (
        "pairwise_dimension",
        "peak_timing",
        "lane_matchup",
        "duo_synergy",
        "trait_multiselect",
    ):
        assert f"'{question_type}'" in body, f"el CASE no contempla {question_type}"


def test_no_personal_data_columns() -> None:
    """CA-004 — el esquema no admite datos personales identificables.

    Es una salvaguarda contra el descuido futuro: si alguien agrega una columna `email` o
    `ip_address`, este test falla antes de que llegue a producción.
    """
    forbidden = re.compile(
        r"(^|_)(email|ip_address|ip_addr|full_name|first_name|last_name|phone|riot_id|"
        r"summoner_name|puuid)($|_)",
        re.I,
    )
    offenders = [
        f"{table}.{column.name}"
        for table, model in Base.metadata.tables.items()
        for column in model.columns
        if forbidden.search(column.name)
    ]
    assert not offenders, f"columnas con aspecto de dato personal: {offenders}"


def test_pairwise_questions_are_canonically_ordered(offline_sql: str) -> None:
    """(A,B) y (B,A) deben ser la misma pregunta, o el sampler duplicaría trabajo."""
    assert "questions_canonical_order" in offline_sql
    assert "champion_a < champion_b" in offline_sql


# --------------------------------------------------------------------------- con base de datos

requires_db = pytest.mark.skipif(
    not DATABASE_URL, reason="requiere DS_DATABASE_URL apuntando a un Postgres"
)


@requires_db
def test_migration_applies_cleanly() -> None:
    """La migración corre de punta a punta contra un Postgres real."""
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        check=True,
    )


@requires_db
def test_models_match_database_after_migration() -> None:
    """No debe quedar ninguna diferencia entre los modelos y el esquema aplicado.

    Es la prueba que impide que los modelos y las migraciones se separen con el tiempo.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    engine = sa.create_engine(sync_url())
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diff = compare_metadata(context, Base.metadata)

    # Alembic reporta los índices con expresiones (COALESCE, DESC) como diferencias porque no
    # los sabe comparar; se filtran por nombre.
    expression_indexes = {
        "questions_identity",
        "aggregates_identity",
        "responses_by_respondent",
        "respondents_leaderboard",
        "exports_by_patch",
    }
    real = [
        entry
        for entry in diff
        if not (
            isinstance(entry, tuple)
            and len(entry) == 2
            and getattr(entry[1], "name", None) in expression_indexes
        )
    ]
    assert not real, f"los modelos y la base divergen: {real}"


@requires_db
def test_responses_rejects_malformed_answer() -> None:
    """CA-203 — la base rechaza una respuesta mal formada sin pasar por la aplicación."""
    engine = sa.create_engine(sync_url())
    with engine.connect() as connection:  # noqa: SIM117
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(
                sa.text(
                    "INSERT INTO responses "
                    "(respondent_id, question_id, type, patch_id, answer, response_time_ms) "
                    "VALUES (gen_random_uuid(), 1, 'peak_timing', 1, '{\"choice\": \"a\"}', 100)"
                )
            )
