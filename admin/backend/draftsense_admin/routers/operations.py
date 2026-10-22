"""Acciones de operación: respondedores, pool, parámetros, parches y seeds (24 §3.4 a §3.9)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter

from draftsense_admin.dependencies import SessionDep, SettingsDep, domain_errors
from draftsense_admin.schemas import (
    ActivateIn,
    ChampionsSeedIn,
    FlagIn,
    HoneypotsSeedIn,
    PickRateSeedIn,
    PoolTierIn,
    SettingIn,
)
from draftsense_admin.services import actions, seeds

router = APIRouter(tags=["operación"])


@router.post("/respondents/{respondent_id}/flag")
async def flag(respondent_id: uuid.UUID, body: FlagIn, session: SessionDep) -> dict[str, Any]:
    with domain_errors():
        return await actions.flag_respondent(session, respondent_id, body.flagged, body.reason)


@router.get("/champions")
async def champions(session: SessionDep) -> dict[str, Any]:
    return await actions.list_champions(session)


@router.patch("/champions/pool-tier")
async def pool_tier(body: PoolTierIn, session: SessionDep) -> dict[str, Any]:
    with domain_errors():
        return await actions.set_pool_tier(session, body.champion_ids, body.pool_tier)


@router.get("/settings")
async def settings(session: SessionDep, config: SettingsDep) -> dict[str, Any]:
    return await actions.list_settings(session, config.seeds_dir)


@router.patch("/settings/{key}")
async def set_setting(key: str, body: SettingIn, session: SessionDep) -> dict[str, Any]:
    with domain_errors():
        return await actions.set_setting(session, key, body.value)


@router.get("/patches")
async def list_patches(session: SessionDep) -> dict[str, Any]:
    return await actions.list_patches(session)


@router.post("/patches/{version}/activate")
async def activate(version: str, body: ActivateIn, session: SessionDep) -> dict[str, Any]:
    with domain_errors():
        return await actions.activate_patch(session, version, body.force)


@router.get("/seeds/files")
async def seed_files(config: SettingsDep) -> dict[str, list[str]]:
    return seeds.list_files(config.seeds_dir)


@router.post("/seeds/champions")
async def seed_champions(
    body: ChampionsSeedIn, session: SessionDep, config: SettingsDep
) -> dict[str, Any]:
    with domain_errors():
        return await seeds.champions(
            session,
            config.seeds_dir,
            base_url=config.ddragon_base_url,
            version=body.version,
            ddragon_version=body.ddragon_version,
            released_at=body.released_at,
            use_snapshot=body.use_snapshot,
        )


@router.post("/seeds/pick-rate")
async def seed_pick_rate(
    body: PickRateSeedIn, session: SessionDep, config: SettingsDep
) -> dict[str, Any]:
    with domain_errors():
        return await seeds.pick_rate(
            session,
            config.seeds_dir,
            version=body.version,
            file=body.file,
            source=body.source,
            source_url=body.source_url,
            captured_at=body.captured_at,
            released_at=body.released_at,
            notes=body.notes,
        )


@router.post("/seeds/honeypots")
async def seed_honeypots(
    body: HoneypotsSeedIn, session: SessionDep, config: SettingsDep
) -> dict[str, Any]:
    with domain_errors():
        return await seeds.honeypots(
            session, config.seeds_dir, version=body.version, file=body.file, force=body.force
        )


@router.get("/exports")
async def exports(session: SessionDep) -> dict[str, Any]:
    return await actions.list_exports(session)
