"""Seeder del catálogo de campeones desde Data Dragon.

Data Dragon es el CDN público de Riot: no requiere clave ni impone cuota. Se consume unas pocas
veces por parche, nunca en el camino de un request.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Champion, LaneRole, Patch

#: Data Dragon clasifica a los campeones por *clase* (Marksman, Tank…), no por carril. Este mapa
#: produce un rol **provisional** para que la fila cumpla `champions_has_roles` desde el primer
#: seed. La fuente autoritativa de roles es el snapshot de pick rate, que sí viene por carril y
#: pisa estos valores al cargarse.
#:
#: Ninguna clase de Data Dragon corresponde a `jungle`: la jungla es una decisión de partida, no
#: una propiedad del campeón. Por eso `assert_roles_covered` avisa y por eso el snapshot de pick
#: rate es un requisito, no una mejora opcional, antes de habilitar los tipos 3 y 4.
PROVISIONAL_ROLE_BY_TAG: dict[str, LaneRole] = {
    "Marksman": LaneRole.ADC,
    "Support": LaneRole.SUPPORT,
    "Mage": LaneRole.MID,
    "Assassin": LaneRole.MID,
    "Fighter": LaneRole.TOP,
    "Tank": LaneRole.TOP,
}


def provisional_roles(tags: list[str]) -> list[LaneRole]:
    """Rol de arranque a partir de las clases de Data Dragon. Ver el comentario del mapa."""
    roles = {PROVISIONAL_ROLE_BY_TAG[t] for t in tags if t in PROVISIONAL_ROLE_BY_TAG}
    return sorted(roles or {LaneRole.MID}, key=lambda r: r.value)


async def roles_without_champions(session: AsyncSession) -> list[LaneRole]:
    """Roles que ningún campeón activo declara.

    Un rol vacío no rompe nada, pero deja tipos de pregunta sin candidatas posibles y eso no
    debe descubrirse recién cuando el sampler devuelve lotes vacíos.
    """
    covered = set(
        (
            await session.execute(
                sa.select(sa.func.unnest(Champion.roles)).where(Champion.is_active)
            )
        )
        .scalars()
        .all()
    )
    return [role for role in LaneRole if role.value not in {str(c) for c in covered}]


async def fetch_latest_version(client: httpx.AsyncClient, base_url: str) -> str:
    response = await client.get(f"{base_url}/api/versions.json", timeout=20)
    response.raise_for_status()
    versions: list[str] = response.json()
    return versions[0]


async def fetch_champion_data(
    client: httpx.AsyncClient, base_url: str, version: str
) -> dict[str, Any]:
    url = f"{base_url}/cdn/{version}/data/en_US/champion.json"
    response = await client.get(url, timeout=30)
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return payload


async def load_champion_data(
    base_url: str, version: str | None, snapshot: Path | None
) -> tuple[str, dict[str, Any]]:
    """Obtiene el catálogo, con respaldo local si Data Dragon no responde.

    El respaldo existe porque el seeder no debe quedar bloqueado por una caída del CDN de Riot
    (§7 del documento de arquitectura).
    """
    try:
        async with httpx.AsyncClient() as client:
            resolved = version or await fetch_latest_version(client, base_url)
            return resolved, await fetch_champion_data(client, base_url, resolved)
    except (httpx.HTTPError, OSError) as exc:
        if snapshot is None or not snapshot.exists():
            raise RuntimeError(
                f"Data Dragon no responde ({exc}) y no hay snapshot local en {snapshot}"
            ) from exc
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        return payload.get("version", version or "unknown"), payload


async def seed_champions(
    session: AsyncSession,
    patch: Patch,
    payload: dict[str, Any],
    ddragon_version: str,
    base_url: str | None = None,
) -> tuple[int, int]:
    """Inserta o actualiza el catálogo. Devuelve (insertados, actualizados).

    Es **idempotente**: re-ejecutarlo en el mismo parche no cambia nada.

    En un conflicto se actualizan sólo los campos que son de Riot —nombre e imagen—. `roles` y
    `pool_tier` **no se tocan**: los corrige el snapshot de pick rate y el administrador, y un
    re-seed no debe pisar ese trabajo.
    """
    base_url = base_url or get_settings().ddragon_base_url
    champions: dict[str, Any] = payload["data"]

    existing = set(
        (await session.execute(sa.select(Champion.riot_key))).scalars().all()
    )

    rows = []
    for key, champion in champions.items():
        rows.append(
            {
                "riot_key": key,
                "riot_name": champion["id"],
                "display_name": champion["name"],
                "roles": provisional_roles(champion.get("tags", [])),
                "image_url": f"{base_url}/cdn/{ddragon_version}/img/champion/{key}.png",
                "patch_first_seen": patch.patch_id,
            }
        )

    statement = pg_insert(Champion).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[Champion.riot_key],
        set_={
            "riot_name": statement.excluded.riot_name,
            "display_name": statement.excluded.display_name,
            "image_url": statement.excluded.image_url,
        },
    )
    await session.execute(statement)
    await session.commit()

    inserted = sum(1 for row in rows if row["riot_key"] not in existing)
    return inserted, len(rows) - inserted
