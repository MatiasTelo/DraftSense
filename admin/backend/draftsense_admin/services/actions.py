"""Las acciones de operación del panel: pool, parámetros, respondedores y parches.

Cada una audita **en la misma transacción** que el cambio, y sólo si cambió algo
(`docs/24-panel-admin.md` §4): mover a un tier que ya tienen, poner el mismo valor o marcar a un
marcado no deja fila, igual que activar el parche vigente (ADR-024).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSetting, Champion, Export, Patch, PickRateEntry, Respondent
from app.seeds.pick_rate import latest_snapshot_id
from app.seeds.settings import load_settings
from app.services import aggregable, app_settings, honeypots, patches, questions
from draftsense_admin.services import audit

#: La única clave con acción propia en el `CHECK` de `admin_audit` (`11-modelo-de-datos.md`
#: §3.13): es la que habilita el tier siguiente, y conviene poder encontrarla sin leer payloads.
ENABLED_TIERS_KEY: Final = "sampler.enabled_pool_tiers"
POOL_TIERS: Final = (1, 2, 3)


class NotFoundError(LookupError):
    """Lo pedido no existe: un respondedor, unos campeones o una clave de `app_settings`."""


# ---------------------------------------------------------------------------- respondedores


async def flag_respondent(
    session: AsyncSession, respondent_id: uuid.UUID, flagged: bool, reason: str
) -> dict[str, Any]:
    """Marca o desmarca a mano (22 §6.3). El motivo sólo vive en la auditoría."""
    respondent = await session.get(Respondent, respondent_id)
    if respondent is None:
        raise NotFoundError(f"no existe el respondedor {respondent_id}")
    previous = respondent.is_flagged
    if previous != flagged:
        respondent.is_flagged = flagged
        audit.record(
            session,
            "flag_respondent",
            {
                "respondent_id": respondent_id,
                "flagged": flagged,
                "previous": previous,
                "reason": reason,
            },
        )
        await session.commit()
    return {"respondent_id": respondent_id, "is_flagged": flagged, "changed": previous != flagged}


# ---------------------------------------------------------------------------------- pool


async def list_champions(session: AsyncSession) -> dict[str, Any]:
    """Los campeones activos, con su mejor puesto en el último snapshot del parche vigente."""
    patch = await questions.current_patch(session)
    snapshot_id = await latest_snapshot_id(session, patch.patch_id) if patch else None
    best: dict[int, int] = {}
    if snapshot_id is not None:
        ranks = await session.execute(
            sa.select(PickRateEntry.champion_id, sa.func.min(PickRateEntry.rank_in_role))
            .where(PickRateEntry.snapshot_id == snapshot_id)
            .group_by(PickRateEntry.champion_id)
        )
        best = {champion_id: rank for champion_id, rank in ranks.tuples()}
    rows = (
        await session.execute(
            sa.select(Champion).where(Champion.is_active).order_by(Champion.display_name)
        )
    ).scalars()
    enabled = int(await app_settings.get(session, ENABLED_TIERS_KEY, 1))
    return {
        "patch": patch.version if patch is not None else None,
        "enabled_pool_tiers": enabled,
        "champions": [
            {
                "champion_id": c.champion_id,
                "name": c.display_name,
                "roles": [role.value for role in c.roles],
                "pool_tier": c.pool_tier,
                "best_rank": best.get(c.champion_id),
            }
            for c in rows
        ],
    }


async def set_pool_tier(
    session: AsyncSession, champion_ids: Sequence[int], pool_tier: int
) -> dict[str, Any]:
    """Mueve campeones de tier: un `UPDATE`, no un despliegue (ADR-006)."""
    if pool_tier not in POOL_TIERS:
        raise ValueError(f"pool_tier tiene que ser uno de {POOL_TIERS}")
    ids = sorted(set(champion_ids))
    if not ids:
        raise ValueError("no se eligió ningún campeón")
    found = set(
        (
            await session.execute(
                sa.select(Champion.champion_id).where(Champion.champion_id.in_(ids))
            )
        ).scalars()
    )
    missing = [i for i in ids if i not in found]
    if missing:
        raise NotFoundError(f"no existen los campeones {missing}")

    changed = list(
        (
            await session.execute(
                sa.update(Champion)
                .where(Champion.champion_id.in_(ids), Champion.pool_tier != pool_tier)
                .values(pool_tier=pool_tier)
                .returning(Champion.champion_id)
            )
        ).scalars()
    )
    if changed:
        audit.record(
            session,
            "set_pool_tier",
            {"champion_ids": sorted(changed), "pool_tier": pool_tier, "updated": len(changed)},
        )
    await session.commit()
    return {"updated": len(changed)}


# ---------------------------------------------------------------------------- parámetros


def _descriptions(seeds_dir: Path) -> dict[str, str]:
    """La descripción de cada clave, del seed. Es ayuda para quien edita, no un dato."""
    try:
        entries = load_settings(seeds_dir)
    except FileNotFoundError:
        return {}
    return {str(e["key"]): str(e.get("description", "")) for e in entries if "key" in e}


async def list_settings(session: AsyncSession, seeds_dir: Path) -> dict[str, Any]:
    rows = (await session.execute(sa.select(AppSetting).order_by(AppSetting.key))).scalars()
    descriptions = _descriptions(seeds_dir)
    return {
        "settings": [
            {
                "key": row.key,
                "block": row.key.split(".", 1)[0],
                "value": row.value,
                "updated_at": row.updated_at,
                "updated_by": row.updated_by,
                "description": descriptions.get(row.key, ""),
            }
            for row in rows
        ]
    }


async def set_setting(session: AsyncSession, key: str, value: Any) -> dict[str, Any]:
    """Cambia una clave que ya existe. Cualquier JSON válido se acepta (24 §3.6).

    No hay esquema por clave en ningún documento y la decisión del 21/10/2026 fue no inventarlo:
    la responsabilidad del valor es de quien lo edita.
    """
    row = await session.get(AppSetting, key)
    if row is None:
        raise NotFoundError(f"no existe la clave {key}: las claves nuevas llegan con un seed")
    previous = row.value
    if previous != value:
        row.value = value
        row.updated_by = "admin"
        row.updated_at = dt.datetime.now(dt.UTC)
        action = "set_enabled_tiers" if key == ENABLED_TIERS_KEY else "set_setting"
        audit.record(session, action, {"key": key, "value": value, "previous": previous})
        await session.commit()
        # La caché de este proceso; la de la API pública vence sola en 60 s (11 §3.12).
        app_settings.reset_cache()
    return {"key": key, "value": value, "previous": previous, "changed": previous != value}


# -------------------------------------------------------------------------------- parches


async def list_patches(session: AsyncSession) -> dict[str, Any]:
    rows = list(
        (await session.execute(sa.select(Patch).order_by(Patch.released_at.desc()))).scalars()
    )
    result = []
    for patch in rows:
        result.append(
            {
                "patch_id": patch.patch_id,
                "version": patch.version,
                "released_at": patch.released_at,
                "is_current": patch.is_current,
                "has_snapshot": await latest_snapshot_id(session, patch.patch_id) is not None,
                "active_honeypots": len(await honeypots.catalog(session, patch.patch_id)),
                "missing": await patches.missing_for(session, patch),
            }
        )
    return {"patches": result}


async def activate_patch(session: AsyncSession, version: str, force: bool) -> dict[str, Any]:
    """`patches.activate` tal cual (ADR-024): el panel no reimplementa sus reglas."""
    result = await patches.activate(session, version, force=force)
    return audit.plain(result)  # type: ignore[no-any-return]


# --------------------------------------------------------------------------- exportaciones


async def list_exports(session: AsyncSession) -> dict[str, Any]:
    """Las corridas anteriores y los valores por defecto del formulario de CU-08 (24 §3.9).

    El botón de generar está deshabilitado hasta la semana 9: no hay nada acá que dispare una
    corrida.
    """
    patch = await questions.current_patch(session)
    rows = (
        await session.execute(sa.select(Export).order_by(Export.created_at.desc()).limit(200))
    ).scalars()
    return {
        "enabled": False,
        "defaults": {
            "patch_window": patch.version if patch is not None else None,
            "min_trust": float(await aggregable.min_trust(session)),
            "decay_halflife_days": await app_settings.get(
                session, "aggregation.decay_halflife_days", None
            ),
            "bootstrap_samples": await app_settings.get(
                session, "aggregation.bootstrap_samples", None
            ),
        },
        "exports": [
            {
                "export_id": e.export_id,
                "file_name": e.file_name,
                "file_kind": e.file_kind,
                "sha256": e.sha256,
                "row_count": e.row_count,
                "patch_window": e.patch_window,
                "min_trust_applied": e.min_trust_applied,
                "created_at": e.created_at,
            }
            for e in rows
        ],
    }
