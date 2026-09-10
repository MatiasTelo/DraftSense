"""Seeder de los parámetros operativos desde `infra/seeds/app_settings.yaml`.

`app_settings` es el estado *actual* del sistema; este seed es sólo el estado *inicial*. Por eso
la carga no pisa los valores existentes: si el panel movió `sampler.epsilon` a 0.20, volver a
correr el seed no puede devolverlo a 1.00 (ver `--force`).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSetting

#: El mismo formato que exige el CHECK `app_settings_key_format`. Validarlo acá permite fallar
#: en `check-seeds`, sin base de datos, en vez de contra un INSERT a medio camino.
KEY_FORMAT = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

SEEDS_DIR = Path(__file__).resolve().parents[3] / "infra" / "seeds"


def load_settings(seeds_dir: Path | None = None) -> list[dict[str, Any]]:
    path = (seeds_dir or SEEDS_DIR) / "app_settings.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} debe contener una lista de entradas")
    return data


def validate_settings(entries: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        key = entry.get("key")
        if not isinstance(key, str):
            problems.append(f"entrada {index}: falta `key`")
            continue
        if not KEY_FORMAT.match(key):
            problems.append(f"entrada {index}: `{key}` no tiene la forma bloque.nombre")
        if key in seen:
            problems.append(f"entrada {index}: clave duplicada '{key}'")
        seen.add(key)
        if "value" not in entry:
            problems.append(f"entrada {index}: `{key}` no tiene `value`")
    return problems


async def seed_settings(
    session: AsyncSession, entries: list[dict[str, Any]], *, force: bool = False
) -> tuple[int, int]:
    """Carga los parámetros. Devuelve (insertados, respetados o pisados).

    Sin `force` la carga es un alta pura: las claves que ya existen conservan su valor, porque
    el valor vigente puede venir del panel y el seed no sabe nada de eso.
    """
    rows = [{"key": e["key"], "value": e["value"], "updated_by": "seed"} for e in entries]
    statement = pg_insert(AppSetting).values(rows)
    if force:
        statement = statement.on_conflict_do_update(
            index_elements=[AppSetting.key],
            set_={"value": statement.excluded.value, "updated_by": statement.excluded.updated_by},
        )
    else:
        statement = statement.on_conflict_do_nothing(index_elements=[AppSetting.key])
    # `RETURNING key` en vez de `rowcount`: con ON CONFLICT DO NOTHING el rowcount del driver no
    # distingue la fila insertada de la salteada, y acá la diferencia es justamente el resultado.
    written = len(
        (await session.execute(statement.returning(AppSetting.key))).scalars().all()
    )
    await session.commit()
    return written, len(rows) - written
