"""Línea de comandos de operación.

    draftsense check-seeds                     valida los YAML sin tocar la base
    draftsense seed-catalog                    carga dimensiones y atributos
    draftsense seed-champions --patch 16.17    puebla el catálogo desde Data Dragon
    draftsense seed-settings                   carga los parámetros operativos
    draftsense seed-pick-rate --patch 16.17    carga el snapshot y asigna el pool
    draftsense fetch-ddragon --out FILE        guarda un snapshot local de respaldo
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

import httpx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_sessionmaker
from app.models import Patch
from app.seeds.catalog import (
    SEEDS_DIR,
    load_yaml,
    seed_dimensions,
    seed_traits,
    validate_entries,
)
from app.seeds.champions import (
    fetch_champion_data,
    fetch_latest_version,
    load_champion_data,
    roles_without_champions,
    seed_champions,
)
from app.seeds.pick_rate import load_pick_rate, seed_pick_rate, validate_pick_rate
from app.seeds.settings import load_settings, seed_settings, validate_settings

DIMENSION_FIELDS = {"code", "label_en", "description_en", "prompt_en"}
TRAIT_FIELDS = {"code", "label_en", "description_en"}

ROLE_WARNING = (
    "       Data Dragon clasifica por clase, no por carril: el rol que asigna el seeder es",
    "       provisional. Cargá el snapshot de pick rate antes de habilitar los tipos de",
    "       pregunta 3 y 4, o el sampler no va a encontrar candidatas.",
)


async def _ensure_patch(
    session: AsyncSession, version: str, released_at: dt.date | None = None
) -> Patch:
    """Devuelve el parche pedido, creándolo si no existe, y lo deja como vigente.

    `released_at` es NOT NULL y no se puede deducir de Data Dragon, que sólo publica la versión.
    Sin `--released-at` se usa la fecha de hoy, que es aproximada: el parche se siembra días
    después de salir. Pasarla explícitamente es lo correcto cuando se la conoce.
    """
    patch = (
        await session.execute(sa.select(Patch).where(Patch.version == version))
    ).scalar_one_or_none()
    if patch is None:
        patch = Patch(
            version=version, released_at=released_at or dt.date.today(), is_current=False
        )
        session.add(patch)
        await session.flush()
    elif released_at is not None:
        patch.released_at = released_at
    # El índice único parcial `patches_single_current` sólo admite un vigente a la vez,
    # así que hay que bajar el anterior antes de subir el nuevo.
    await session.execute(sa.update(Patch).values(is_current=False))
    await session.execute(
        sa.update(Patch).where(Patch.patch_id == patch.patch_id).values(is_current=True)
    )
    await session.commit()
    return patch


def _released_at(args: argparse.Namespace) -> dt.date | None:
    value = getattr(args, "released_at", None)
    return dt.date.fromisoformat(value) if value else None


async def cmd_check_seeds(args: argparse.Namespace) -> int:
    seeds_dir = Path(args.seeds_dir) if args.seeds_dir else None
    dimensions = load_yaml("dimensions.yaml", seeds_dir)
    traits = load_yaml("traits.yaml", seeds_dir)

    settings_entries = load_settings(seeds_dir)

    problems = [f"dimensions.yaml: {p}" for p in validate_entries(dimensions, DIMENSION_FIELDS)]
    problems += [f"traits.yaml: {p}" for p in validate_entries(traits, TRAIT_FIELDS)]
    problems += [f"app_settings.yaml: {p}" for p in validate_settings(settings_entries)]

    # Los snapshots de pick rate se acumulan, uno por parche: se validan todos los que haya.
    snapshots = sorted((seeds_dir or SEEDS_DIR).glob("pick_rate_*.csv"))
    n_entries = 0
    for path in snapshots:
        rows = load_pick_rate(path)
        n_entries += len(rows)
        problems += [f"{path.name}: {p}" for p in validate_pick_rate(rows)]

    if problems:
        for problem in problems:
            print(f"ERROR {problem}", file=sys.stderr)
        return 1

    print(
        f"OK  {len(dimensions)} dimensiones, {len(traits)} atributos, "
        f"{len(settings_entries)} parámetros, "
        f"{n_entries} entradas de pick rate en {len(snapshots)} snapshot(s)"
    )
    return 0


async def cmd_seed_catalog(args: argparse.Namespace) -> int:
    seeds_dir = Path(args.seeds_dir) if args.seeds_dir else None
    dimensions = load_yaml("dimensions.yaml", seeds_dir)
    traits = load_yaml("traits.yaml", seeds_dir)
    async with get_sessionmaker()() as session:
        n_dimensions = await seed_dimensions(session, dimensions)
        n_traits = await seed_traits(session, traits)
    print(f"OK  {n_dimensions} dimensiones, {n_traits} atributos")
    return 0


async def cmd_seed_champions(args: argparse.Namespace) -> int:
    settings = get_settings()
    snapshot = Path(args.snapshot) if args.snapshot else None
    ddragon_version, payload = await load_champion_data(
        settings.ddragon_base_url, args.ddragon_version, snapshot
    )

    async with get_sessionmaker()() as session:
        patch = await _ensure_patch(session, args.patch, _released_at(args))
        inserted, updated = await seed_champions(
            session, patch, payload, ddragon_version, settings.ddragon_base_url
        )
        missing = await roles_without_champions(session)

    print(
        f"OK  parche {args.patch} (Data Dragon {ddragon_version}): "
        f"{inserted} campeones nuevos, {updated} actualizados"
    )
    if missing:
        roles = ", ".join(role.value for role in missing)
        print(f"AVISO  ningún campeón activo declara el rol: {roles}.", file=sys.stderr)
        for line in ROLE_WARNING:
            print(line, file=sys.stderr)
    return 0


async def cmd_seed_settings(args: argparse.Namespace) -> int:
    seeds_dir = Path(args.seeds_dir) if args.seeds_dir else None
    entries = load_settings(seeds_dir)
    async with get_sessionmaker()() as session:
        written, kept = await seed_settings(session, entries, force=args.force)
    if args.force:
        print(f"OK  {len(entries)} parámetros escritos (--force pisó los existentes)")
    else:
        print(f"OK  {written} parámetros nuevos, {kept} ya existían y se respetaron")
    return 0


async def cmd_seed_pick_rate(args: argparse.Namespace) -> int:
    path = Path(args.file)
    rows = load_pick_rate(path)
    problems = validate_pick_rate(rows)
    if problems:
        for problem in problems:
            print(f"ERROR {path.name}: {problem}", file=sys.stderr)
        return 1

    async with get_sessionmaker()() as session:
        patch = await _ensure_patch(session, args.patch, _released_at(args))
        loaded, counts, unmatched = await seed_pick_rate(
            session,
            patch_id=patch.patch_id,
            rows=rows,
            source=args.source,
            source_url=args.source_url,
            captured_at=dt.date.fromisoformat(args.captured_at),
            notes=args.notes,
        )

    print(
        f"OK  parche {args.patch}: {loaded} entradas de pick rate · "
        f"pool tier 1: {counts[1]}, tier 2: {counts[2]}, tier 3: {counts[3]}"
    )
    if unmatched:
        print(
            f"AVISO  {len(unmatched)} nombres del snapshot no están en el catálogo: "
            f"{', '.join(unmatched)}",
            file=sys.stderr,
        )
        print(
            "       Corré `seed-champions` contra el mismo parche antes de cargar el snapshot.",
            file=sys.stderr,
        )
    return 0

async def cmd_fetch_ddragon(args: argparse.Namespace) -> int:
    """Guarda un snapshot del catálogo, como respaldo para cuando Data Dragon no responda."""
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        version = args.ddragon_version or await fetch_latest_version(
            client, settings.ddragon_base_url
        )
        payload = await fetch_champion_data(client, settings.ddragon_base_url, version)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK  Data Dragon {version}: {len(payload['data'])} campeones -> {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="draftsense", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check-seeds", help="valida los YAML sin tocar la base")
    check.add_argument("--seeds-dir")
    check.set_defaults(handler=cmd_check_seeds)

    catalog = sub.add_parser("seed-catalog", help="carga dimensiones y atributos")
    catalog.add_argument("--seeds-dir")
    catalog.set_defaults(handler=cmd_seed_catalog)

    champions = sub.add_parser("seed-champions", help="puebla el catálogo desde Data Dragon")
    champions.add_argument("--patch", required=True, help="versión del parche, p. ej. 16.17")
    champions.add_argument("--ddragon-version", help="por defecto, la última publicada")
    champions.add_argument("--snapshot", help="respaldo local si el CDN no responde")
    champions.add_argument("--released-at", help="fecha de salida del parche, AAAA-MM-DD")
    champions.set_defaults(handler=cmd_seed_champions)

    settings_cmd = sub.add_parser("seed-settings", help="carga los parámetros operativos")
    settings_cmd.add_argument("--seeds-dir")
    settings_cmd.add_argument(
        "--force",
        action="store_true",
        help="pisa los valores existentes; sin esto el seed sólo da de alta las claves nuevas",
    )
    settings_cmd.set_defaults(handler=cmd_seed_settings)

    pick = sub.add_parser("seed-pick-rate", help="carga el snapshot y asigna el pool escalonado")
    pick.add_argument("--patch", required=True, help="versión del parche, p. ej. 16.17")
    pick.add_argument("--file", required=True, help="CSV del snapshot")
    pick.add_argument("--source", default="lolalytics")
    pick.add_argument(
        "--source-url", required=True, help="la URL exacta de la captura, con sus filtros"
    )
    pick.add_argument("--captured-at", required=True, help="fecha de la captura, AAAA-MM-DD")
    pick.add_argument("--released-at", help="fecha de salida del parche, AAAA-MM-DD")
    pick.add_argument("--notes")
    pick.set_defaults(handler=cmd_seed_pick_rate)

    fetch = sub.add_parser("fetch-ddragon", help="guarda un snapshot local de respaldo")
    fetch.add_argument("--out", required=True)
    fetch.add_argument("--ddragon-version")
    fetch.set_defaults(handler=cmd_fetch_ddragon)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    exit_code: int = asyncio.run(args.handler(args))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
