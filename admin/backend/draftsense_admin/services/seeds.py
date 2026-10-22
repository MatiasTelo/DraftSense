"""Los tres seeds de CU-06 desde el panel (`docs/24-panel-admin.md` §3.8).

El panel **no sube archivos**: elige entre los que ya están en `infra/seeds/` del servidor. El
nombre que llega del navegador se busca en esa lista y nunca se usa para armar una ruta, así que
`../backend/.env` no es un archivo que se pueda pedir (CA-611).

El camino de cada seed es el mismo que el del CLI, `app.services.seeding`. Lo único propio de acá
es la auditoría: los services del backend ya hacen commit, así que la fila `run_seed` se escribe
después, en su propia transacción, y sólo si el seed terminó bien.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import seeding
from draftsense_admin.services import audit

#: Qué archivos de `infra/seeds/` ofrece cada paso.
PATTERNS: Final = {
    "pick_rate": "pick_rate_*.csv",
    "honeypots": "honeypots_*.yaml",
    "ddragon_snapshot": "ddragon_champions_*.json",
}


class SeedFileNotAllowedError(ValueError):
    """El nombre no es uno de los archivos que ofrece el panel."""


def list_files(seeds_dir: Path) -> dict[str, list[str]]:
    return {
        kind: sorted(p.name for p in seeds_dir.glob(pattern) if p.is_file())
        for kind, pattern in PATTERNS.items()
    }


def resolve(seeds_dir: Path, kind: str, name: str) -> Path:
    """La ruta del archivo elegido, si y sólo si está en la lista de su tipo."""
    if name not in list_files(seeds_dir).get(kind, []):
        raise SeedFileNotAllowedError(f"{name!r} no es un archivo de {kind} de infra/seeds/")
    return seeds_dir / name


async def _audit(
    session: AsyncSession, seed: str, patch: str, file: str | None, params: Any, result: Any
) -> None:
    audit.record(
        session,
        "run_seed",
        {"seed": seed, "patch": patch, "file": file, "params": params, "result": result},
    )
    await session.commit()


async def champions(
    session: AsyncSession,
    seeds_dir: Path,
    *,
    base_url: str,
    version: str,
    ddragon_version: str | None,
    released_at: dt.date | None,
    use_snapshot: bool,
) -> dict[str, Any]:
    """Paso 1. Con `use_snapshot` usa el respaldo local en vez de Data Dragon."""
    snapshot: Path | None = None
    file: str | None = None
    if use_snapshot:
        files = list_files(seeds_dir)["ddragon_snapshot"]
        if not files:
            raise SeedFileNotAllowedError("no hay respaldo de Data Dragon en infra/seeds/")
        file = files[0]
        snapshot = seeds_dir / file
    loaded = await seeding.load_champions(
        session,
        version,
        base_url=base_url,
        ddragon_version=ddragon_version,
        snapshot=snapshot,
        released_at=released_at,
    )
    result = audit.plain(loaded)
    params = {"ddragon_version": ddragon_version, "released_at": released_at}
    await _audit(session, "champions", version, file, audit.plain(params), result)
    warnings = []
    if loaded.missing_roles:
        warnings.append(
            "ningún campeón activo declara el rol: " + ", ".join(loaded.missing_roles)
            + ". Cargá el snapshot de pick rate antes de habilitar los tipos 3 y 4."
        )
    return {"result": result, "warnings": warnings}


async def pick_rate(
    session: AsyncSession,
    seeds_dir: Path,
    *,
    version: str,
    file: str,
    source: str,
    source_url: str,
    captured_at: dt.date,
    released_at: dt.date | None,
    notes: str | None,
) -> dict[str, Any]:
    """Paso 2."""
    path = resolve(seeds_dir, "pick_rate", file)
    loaded = await seeding.load_pick_rate_file(
        session,
        version,
        path,
        source=source,
        source_url=source_url,
        captured_at=captured_at,
        released_at=released_at,
        notes=notes,
    )
    result = audit.plain(loaded)
    params = {
        "source": source,
        "source_url": source_url,
        "captured_at": captured_at,
        "released_at": released_at,
        "notes": notes,
    }
    await _audit(session, "pick_rate", version, file, audit.plain(params), result)
    warnings = []
    if loaded.unmatched:
        warnings.append(
            f"{len(loaded.unmatched)} nombres del snapshot no están en el catálogo: "
            + ", ".join(loaded.unmatched)
            + ". Cargá el catálogo de campeones del mismo parche antes del snapshot."
        )
    return {"result": result, "warnings": warnings}


async def honeypots(
    session: AsyncSession, seeds_dir: Path, *, version: str, file: str, force: bool
) -> dict[str, Any]:
    """Paso 3. `force` reactiva las honeypots que el monitoreo de pass rate retiró."""
    path = resolve(seeds_dir, "honeypots", file)
    loaded = await seeding.load_honeypot_file(session, version, path, force=force)
    result = audit.plain(loaded)
    await _audit(session, "honeypots", version, file, {"force": force}, result)
    return {"result": result, "warnings": list(loaded.skipped)}
