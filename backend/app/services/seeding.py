"""Los tres seeds de un parche nuevo, de punta a punta: leer el archivo, validarlo y cargarlo.

Hasta la semana 6 este camino vivía en los `cmd_*` de `app/cli.py`. Desde la semana 7 también lo
recorre la app de administración local (ADR-025), y tenerlo en dos lugares era la forma segura de
que el panel y el CLI terminaran validando distinto. Los dos llaman a estas funciones; lo único que
les queda propio es cómo muestran el resultado.

Ninguna función audita: el CLI no audita, y el panel escribe su fila de `run_seed` al terminar
(`docs/24-panel-admin.md` §4).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Patch
from app.seeds.champions import load_champion_data, roles_without_champions, seed_champions
from app.seeds.honeypots import (
    HoneypotCatalogError,
    SeedHoneypotsResult,
    load_honeypots,
    seed_honeypots,
    validate_honeypots,
)
from app.seeds.pick_rate import PickRateResult, load_pick_rate, seed_pick_rate, validate_pick_rate
from app.services import patches


class SeedFileError(ValueError):
    """El archivo no pasa la validación de forma, o nombra algo que la base no tiene."""

    def __init__(self, path: Path, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.path = path
        self.problems = problems


@dataclass(frozen=True, slots=True)
class ChampionsLoad:
    version: str
    ddragon_version: str
    inserted: int
    updated: int
    #: Roles que ningún campeón activo declara después de la carga.
    missing_roles: list[str] = field(default_factory=list)


async def load_champions(
    session: AsyncSession,
    version: str,
    *,
    base_url: str,
    ddragon_version: str | None = None,
    snapshot: Path | None = None,
    released_at: dt.date | None = None,
) -> ChampionsLoad:
    """Relee el catálogo de Data Dragon (o el respaldo local) y registra el parche (ADR-024)."""
    resolved, payload = await load_champion_data(base_url, ddragon_version, snapshot)
    patch = await patches.register(session, version, released_at)
    inserted, updated = await seed_champions(session, patch, payload, resolved, base_url)
    missing = await roles_without_champions(session)
    return ChampionsLoad(
        version=version,
        ddragon_version=resolved,
        inserted=inserted,
        updated=updated,
        missing_roles=[role.value for role in missing],
    )


async def load_pick_rate_file(
    session: AsyncSession,
    version: str,
    path: Path,
    *,
    source: str,
    source_url: str,
    captured_at: dt.date,
    released_at: dt.date | None = None,
    notes: str | None = None,
) -> PickRateResult:
    """Valida el CSV antes de tocar la base y lo carga contra el parche, registrándolo si falta."""
    rows = load_pick_rate(path)
    problems = validate_pick_rate(rows)
    if problems:
        raise SeedFileError(path, problems)
    patch = await patches.register(session, version, released_at)
    return await seed_pick_rate(
        session,
        patch_id=patch.patch_id,
        rows=rows,
        source=source,
        source_url=source_url,
        captured_at=captured_at,
        notes=notes,
    )


async def load_honeypot_file(
    session: AsyncSession, version: str, path: Path, *, force: bool = False
) -> SeedHoneypotsResult:
    """Carga el catálogo de honeypots de un parche **que ya existe** (22 §3.3).

    No registra el parche: las honeypots se escriben contra un catálogo de campeones ya sembrado,
    con su pool asignado, y crear el parche acá escondería que falta ese paso.
    """
    entries = load_honeypots(path)
    problems = validate_honeypots(entries)
    if problems:
        raise SeedFileError(path, problems)
    patch = (
        await session.execute(sa.select(Patch).where(Patch.version == version))
    ).scalar_one_or_none()
    if patch is None:
        raise patches.PatchNotFoundError([f"no existe el parche {version}"])
    try:
        return await seed_honeypots(session, patch.patch_id, entries, force=force)
    except HoneypotCatalogError as exc:
        raise SeedFileError(path, exc.problems) from exc
