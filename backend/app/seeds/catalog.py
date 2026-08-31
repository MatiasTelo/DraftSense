"""Seeder de dimensiones y atributos desde los YAML versionados en `infra/seeds/`.

Los seeds no viven en migraciones: son datos de catálogo que cambian por decisión de producto,
no por evolución del esquema. Mantenerlos como archivos versionados permite agregar una dimensión
con un `git diff` legible y sin generar una migración (RF-603).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dimension, Trait

SEEDS_DIR = Path(__file__).resolve().parents[3] / "infra" / "seeds"


def load_yaml(name: str, seeds_dir: Path | None = None) -> list[dict[str, Any]]:
    path = (seeds_dir or SEEDS_DIR) / name
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} debe contener una lista de entradas")
    return data


async def seed_dimensions(session: AsyncSession, entries: list[dict[str, Any]]) -> int:
    """Carga las dimensiones. Idempotente por `code`."""
    statement = pg_insert(Dimension).values(entries)
    statement = statement.on_conflict_do_update(
        index_elements=[Dimension.code],
        set_={
            "label_en": statement.excluded.label_en,
            "description_en": statement.excluded.description_en,
            "prompt_en": statement.excluded.prompt_en,
            "display_order": statement.excluded.display_order,
        },
    )
    await session.execute(statement)
    await session.commit()
    return len(entries)


async def seed_traits(session: AsyncSession, entries: list[dict[str, Any]]) -> int:
    """Carga los atributos. Idempotente por `code`."""
    statement = pg_insert(Trait).values(entries)
    statement = statement.on_conflict_do_update(
        index_elements=[Trait.code],
        set_={
            "label_en": statement.excluded.label_en,
            "description_en": statement.excluded.description_en,
            "legacy_tag": statement.excluded.legacy_tag,
            "display_order": statement.excluded.display_order,
        },
    )
    await session.execute(statement)
    await session.commit()
    return len(entries)


def validate_entries(entries: list[dict[str, Any]], required: set[str]) -> list[str]:
    """Errores de forma del seed, para fallar antes de tocar la base."""
    problems: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        missing = required - set(entry)
        if missing:
            problems.append(f"entrada {index}: faltan campos {sorted(missing)}")
        code = entry.get("code")
        if code in seen:
            problems.append(f"entrada {index}: código duplicado '{code}'")
        if isinstance(code, str):
            seen.add(code)
    return problems
