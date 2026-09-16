"""Los roles de cada campeón salen del snapshot de pick rate (ADR-019).

Hasta la semana 4 `seed-pick-rate` asignaba el tier y dejaba los roles provisorios de Data Dragon,
que se equivocan en 38 de los 58 campeones del tier 1. El tipo 3 empareja por rol, así que un rol
mal cargado produce enfrentamientos que nadie juega.

Ningún test ejecuta los comandos del CLI contra la base: abren su propia sesión con
`get_sessionmaker()` y escaparían de la transacción que el test revierte, escribiendo en staging
de verdad. Se prueban los services que los comandos llaman.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.cli import build_parser, cmd_sync_roles
from app.models import Champion, LaneRole, Patch, PickRateEntry, PickRateSnapshot
from app.seeds.pick_rate import (
    SnapshotRow,
    latest_snapshot_id,
    roles_by_champion,
    seed_pick_rate,
    sync_roles,
)
from tests.conftest import requires_db


async def _snapshot(
    db: AsyncSession,
    patch: Patch,
    captured_at: dt.date,
    entries: list[tuple[Champion, LaneRole, int]],
) -> int:
    """Un snapshot con sus entradas: (campeón, rol, puesto en el rol)."""
    snapshot = PickRateSnapshot(
        source="lolalytics",
        source_url="https://example.invalid/tierlist",
        captured_at=captured_at,
        patch_id=patch.patch_id,
    )
    db.add(snapshot)
    await db.flush()
    db.add_all(
        [
            PickRateEntry(
                snapshot_id=snapshot.snapshot_id,
                champion_id=champion.champion_id,
                role=role,
                pick_rate=Decimal("0.0500"),
                rank_in_role=rank,
            )
            for champion, role, rank in entries
        ]
    )
    await db.commit()
    return snapshot.snapshot_id


async def _roles(db: AsyncSession, champion: Champion) -> list[str]:
    await db.refresh(champion)
    return [str(role) for role in champion.roles]


def test_los_roles_son_todos_los_del_snapshot() -> None:
    """Cada carril en el que aparece, sin repetir y ordenados por valor, como los provisorios."""
    entries = [
        (1, LaneRole.TOP),
        (1, LaneRole.JUNGLE),
        (1, LaneRole.TOP),
        (2, LaneRole.ADC),
    ]
    assert roles_by_champion(entries) == {
        1: [LaneRole.JUNGLE, LaneRole.TOP],
        2: [LaneRole.ADC],
    }


def test_el_comando_sync_roles_esta_registrado() -> None:
    args = build_parser().parse_args(["sync-roles", "--patch", "16.17"])
    assert args.handler is cmd_sync_roles
    assert args.patch == "16.17"


@requires_db
async def test_sync_roles_pisa_los_provisionales_y_respeta_a_los_ausentes(
    db: AsyncSession, patch: Patch, champions: list[Champion]
) -> None:
    """ADR-019 — el que figura toma sus carriles; el que no figura conserva los que tenía."""
    present, absent = champions[0], champions[1]
    snapshot_id = await _snapshot(
        db,
        patch,
        dt.date(2026, 9, 9),
        [(present, LaneRole.JUNGLE, 1), (present, LaneRole.TOP, 5)],
    )

    updated = await sync_roles(db, snapshot_id)
    await db.commit()

    assert updated == 1
    assert await _roles(db, present) == ["jungle", "top"]
    assert await _roles(db, absent) == ["mid"]


@requires_db
async def test_sync_roles_usa_el_ultimo_snapshot_del_parche(
    db: AsyncSession, patch: Patch, champions: list[Champion]
) -> None:
    champion = champions[0]
    await _snapshot(db, patch, dt.date(2026, 9, 1), [(champion, LaneRole.TOP, 3)])
    latest = await _snapshot(db, patch, dt.date(2026, 9, 9), [(champion, LaneRole.ADC, 2)])

    assert await latest_snapshot_id(db, patch.patch_id) == latest

    await sync_roles(db, latest)
    await db.commit()

    assert await _roles(db, champion) == ["adc"]


@requires_db
async def test_sync_roles_es_idempotente(
    db: AsyncSession, patch: Patch, champions: list[Champion]
) -> None:
    champion = champions[0]
    snapshot_id = await _snapshot(
        db, patch, dt.date(2026, 9, 9), [(champion, LaneRole.SUPPORT, 4)]
    )

    await sync_roles(db, snapshot_id)
    await db.commit()
    first = await _roles(db, champion)

    await sync_roles(db, snapshot_id)
    await db.commit()

    assert await _roles(db, champion) == first == ["support"]


@requires_db
async def test_sin_snapshot_no_hay_nada_que_sincronizar(db: AsyncSession, patch: Patch) -> None:
    assert await latest_snapshot_id(db, patch.patch_id) is None


@requires_db
async def test_seed_pick_rate_sincroniza_los_roles(
    db: AsyncSession, patch: Patch, champions: list[Champion]
) -> None:
    """La carga de un snapshot nuevo aplica la regla sin un paso aparte."""
    rows = [
        SnapshotRow(LaneRole.ADC, champions[0].display_name, Decimal("0.0800"), 1),
        SnapshotRow(LaneRole.SUPPORT, champions[0].display_name, Decimal("0.0100"), 30),
        SnapshotRow(LaneRole.TOP, champions[1].display_name, Decimal("0.0700"), 2),
    ]

    result = await seed_pick_rate(
        db,
        patch_id=patch.patch_id,
        rows=rows,
        source="lolalytics",
        source_url="https://example.invalid/tierlist",
        captured_at=dt.date(2026, 9, 9),
    )

    assert result.loaded == 3
    assert result.roles_updated == 2
    assert await _roles(db, champions[0]) == ["adc", "support"]
    assert await _roles(db, champions[1]) == ["top"]
    assert await _roles(db, champions[2]) == ["mid"]
