"""Carga del snapshot de pick rate y asignación del pool escalonado.

El snapshot es la única fuente del pool: `pool_tier` se deriva de él con la regla de
`docs/21-sampler.md` §7.1, no de un juicio del administrador (ADR-006, ADR-016).
"""

from __future__ import annotations

import csv
import datetime as dt
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Champion, LaneRole, PickRateEntry, PickRateSnapshot

SEEDS_DIR = Path(__file__).resolve().parents[3] / "infra" / "seeds"

#: Los dos cortes de `docs/21-sampler.md` §7.1, aplicados a la carga inicial por ADR-016.
#: Entrar al top 12 de ALGÚN rol basta: un campeón que sólo se juega en un carril no vale menos
#: que uno que se reparte entre dos.
TIER_1_RANK = 12
TIER_2_RANK = 20


class SnapshotRow(NamedTuple):
    role: LaneRole
    champion_name: str
    pick_rate: Decimal
    rank_in_role: int


def load_pick_rate(path: Path) -> list[SnapshotRow]:
    """Lee el CSV, salteando las líneas de comentario de la cabecera."""
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    rows: list[SnapshotRow] = []
    for raw in csv.DictReader(lines):
        rows.append(
            SnapshotRow(
                role=LaneRole(raw["role"]),
                champion_name=raw["champion_name"],
                pick_rate=Decimal(raw["pick_rate"]),
                rank_in_role=int(raw["rank_in_role"]),
            )
        )
    return rows


def validate_pick_rate(rows: list[SnapshotRow]) -> list[str]:
    problems: list[str] = []
    if not rows:
        return ["el snapshot no tiene ninguna fila"]
    seen: set[tuple[LaneRole, str]] = set()
    ranks: dict[LaneRole, set[int]] = {}
    for row in rows:
        if not (0 < row.pick_rate <= 1):
            problems.append(f"{row.role.value}/{row.champion_name}: pick_rate fuera de (0, 1]")
        key = (row.role, row.champion_name)
        if key in seen:
            problems.append(f"{row.role.value}/{row.champion_name}: entrada duplicada")
        seen.add(key)
        if row.rank_in_role in ranks.setdefault(row.role, set()):
            problems.append(f"{row.role.value}: rank_in_role {row.rank_in_role} repetido")
        ranks[row.role].add(row.rank_in_role)
    for role, values in ranks.items():
        expected = set(range(1, max(values) + 1))
        if values != expected:
            problems.append(f"{role.value}: los rank_in_role no son 1..{max(values)} sin huecos")
    return problems


def tier_for(best_rank: int) -> int:
    """El tier que le corresponde a un campeón según su mejor puesto entre todos sus roles."""
    if best_rank <= TIER_1_RANK:
        return 1
    if best_rank <= TIER_2_RANK:
        return 2
    return 3


async def seed_pick_rate(
    session: AsyncSession,
    *,
    patch_id: int,
    rows: list[SnapshotRow],
    source: str,
    source_url: str,
    captured_at: dt.date,
    notes: str | None = None,
) -> tuple[int, dict[int, int], list[str]]:
    """Registra el snapshot y reasigna `pool_tier`.

    Devuelve (entradas cargadas, campeones por tier, nombres sin correspondencia en el catálogo).
    Los nombres que no resuelven **no se descartan en silencio**: se devuelven para que el
    comando los informe. Un campeón que el snapshot menciona y el catálogo no tiene significa
    que `seed-champions` corrió contra otro parche.
    """
    by_name = {
        name: champion_id
        for champion_id, name in (
            await session.execute(sa.select(Champion.champion_id, Champion.display_name))
        ).all()
    }
    unmatched = sorted({r.champion_name for r in rows if r.champion_name not in by_name})
    matched = [r for r in rows if r.champion_name in by_name]

    snapshot = PickRateSnapshot(
        source=source,
        source_url=source_url,
        captured_at=captured_at,
        patch_id=patch_id,
        notes=notes,
    )
    session.add(snapshot)
    await session.flush()

    session.add_all(
        [
            PickRateEntry(
                snapshot_id=snapshot.snapshot_id,
                champion_id=by_name[r.champion_name],
                role=r.role,
                pick_rate=r.pick_rate,
                rank_in_role=r.rank_in_role,
            )
            for r in matched
        ]
    )

    best: dict[int, int] = {}
    for row in matched:
        champion_id = by_name[row.champion_name]
        best[champion_id] = min(best.get(champion_id, row.rank_in_role), row.rank_in_role)

    # Todo campeón fuera del snapshot vuelve a tier 3: el pool es un derivado del snapshot
    # vigente, no un acumulado de todos los que alguna vez estuvieron.
    await session.execute(sa.update(Champion).values(pool_tier=3))
    counts = {1: 0, 2: 0, 3: 0}
    for champion_id, rank in best.items():
        tier = tier_for(rank)
        counts[tier] += 1
        await session.execute(
            sa.update(Champion)
            .where(Champion.champion_id == champion_id)
            .values(pool_tier=tier)
        )
    counts[3] = len(by_name) - counts[1] - counts[2]

    await session.commit()
    return len(matched), counts, unmatched
