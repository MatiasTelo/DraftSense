#!/usr/bin/env python3
"""Verifica la documentación de `docs/`.

Corre en CI y también a mano. Comprueba tres cosas que se rompen solas con el tiempo:

1. El DDL de `11-modelo-de-datos.md` parsea como Postgres válido, y sus claves foráneas e
   índices apuntan a tablas que existen.
2. Ningún enlace interno entre documentos está roto.
3. Los conteos de columnas que declara `26-esquema-de-salida.md` coinciden con su desglose.

Requiere `sqlglot`.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import sqlglot
from sqlglot import expressions as exp
from sqlglot.errors import ParseError

# sqlglot avisa por consola cada vez que degrada una sentencia; lo detectamos nosotros.
logging.getLogger("sqlglot").setLevel(logging.ERROR)

DOCS = Path(__file__).resolve().parents[1] / "docs"

#: Sentencias que sqlglot no sabe parsear y devuelve como texto crudo, sin validar nada.
#: Se toleran de a una y por nombre: si aparece cualquier otra, es que se colo un error de
#: sintaxis o que hay sintaxis nueva que hay que revisar a mano.
UNPARSEABLE_BY_SQLGLOT = {
    # NULLS NOT DISTINCT es de Postgres 15; sqlglot 30 todavia no lo modela.
    "CREATE UNIQUE INDEX questions_identity",
    "CREATE UNIQUE INDEX aggregates_identity",
    # sqlglot no modela CREATE EXTENSION en ningun dialecto.
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
}

#: Bloques del CSV de campeones: cuántas columnas aporta cada uno.
CHAMPION_FEATURE_BLOCKS = {
    "identificación": 7,
    "dimensiones (8 x 7)": 8 * 7,
    "pico de poder": 10,
    "fuerza de línea (3 x 5)": 3 * 5,
    "sinergia": 3,
    "atributos (7 x 5)": 7 * 5,
}
#: Magnitudes medidas por campeón: 8 dimensiones + pico + 3 líneas + sinergia + 7 atributos.
CHAMPION_MAGNITUDES = 8 + 1 + 3 + 1 + 7

EXPECTED_TABLES = {
    "patches",
    "champions",
    "pick_rate_snapshots",
    "pick_rate_entries",
    "dimensions",
    "traits",
    "respondents",
    "questions",
    "responses",
    "aggregates",
    "exports",
    "app_settings",
    "admin_audit",
}


def check_ddl(errors: list[str]) -> None:
    text = (DOCS / "11-modelo-de-datos.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```sql\n(.*?)```", text, re.DOTALL)
    print(f"bloques SQL: {len(blocks)}")

    parsed = 0
    degraded: list[str] = []
    for index, block in enumerate(blocks, 1):
        # El bloque de permisos usa variables de psql (:'clave'), que no son SQL puro.
        if ":'" in block:
            continue
        for statement in sqlglot.parse(block, read="postgres"):
            if statement is None:
                continue
            parsed += 1
            if isinstance(statement, exp.Command):
                # sqlglot no la entendio: la devolvio como texto y no valido nada.
                sql = statement.sql(dialect="postgres", comments=False)
                head = " ".join(sql.split())[:60]
                if not any(head.startswith(known) for known in UNPARSEABLE_BY_SQLGLOT):
                    errors.append(f"DDL, bloque {index}: sqlglot no pudo parsear `{head}`")
                else:
                    degraded.append(head.split("(")[0].strip())
                continue
            try:
                sqlglot.transpile(statement.sql(dialect="postgres"), read="postgres")
            except ParseError as exc:
                errors.append(f"DDL, bloque {index}: {exc}")
    print(f"sentencias parseadas: {parsed - len(degraded)} de {parsed}")
    for head in degraded:
        print(f"  sin validar (sintaxis que sqlglot no modela): {head}")

    tables = set(re.findall(r"CREATE TABLE (\w+)", text))
    missing = EXPECTED_TABLES - tables
    if missing:
        errors.append(f"tablas faltantes en el DDL: {sorted(missing)}")

    for target in set(re.findall(r"REFERENCES (\w+)", text)):
        if target not in tables:
            errors.append(f"clave foránea hacia una tabla inexistente: {target}")

    for name, table in re.findall(r"CREATE (?:UNIQUE )?INDEX (\w+)\s+ON (\w+)", text):
        if table not in tables:
            errors.append(f"índice {name} sobre una tabla inexistente: {table}")

    print(f"tablas definidas: {len(tables)}")


def check_links(errors: list[str]) -> None:
    pattern = re.compile(r"\[[^\]]*\]\(([^)#][^)]*)\)")
    checked = 0
    for path in DOCS.rglob("*.md"):
        for target in pattern.findall(path.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            checked += 1
            if not (path.parent / target).resolve().exists():
                errors.append(f"enlace roto en {path.relative_to(DOCS)}: {target}")
    print(f"enlaces internos verificados: {checked}")


def check_output_schema(errors: list[str]) -> None:
    text = (DOCS / "26-esquema-de-salida.md").read_text(encoding="utf-8")
    total = sum(CHAMPION_FEATURE_BLOCKS.values())
    print(f"columnas de champion_features: {total}, magnitudes: {CHAMPION_MAGNITUDES}")
    if f"{total} columnas" not in text:
        errors.append(f"26-esquema-de-salida.md no declara '{total} columnas'")
    if f"{CHAMPION_MAGNITUDES} magnitudes" not in text:
        errors.append(f"26-esquema-de-salida.md no declara '{CHAMPION_MAGNITUDES} magnitudes'")


def main() -> int:
    errors: list[str] = []
    check_ddl(errors)
    check_links(errors)
    check_output_schema(errors)

    if errors:
        print("\nERRORES:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("\nTODO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
