"""Las acciones de operación y su auditoría (CA-604, CA-609, `docs/24-panel-admin.md` §4)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAudit, Champion, Patch
from tests.conftest import make_champions, make_respondent, requires_db, set_setting

pytestmark = requires_db


async def audit_rows(db: AsyncSession, action: str | None = None) -> list[AdminAudit]:
    statement = sa.select(AdminAudit).order_by(AdminAudit.audit_id)
    if action:
        statement = statement.where(AdminAudit.action == action)
    return list((await db.execute(statement)).scalars())


async def count_audit(db: AsyncSession) -> int:
    return (await db.execute(sa.select(sa.func.count()).select_from(AdminAudit))).scalar_one()


# ---------------------------------------------------------------------------- respondedores


async def test_flag_and_unflag_are_audited_once(client: AsyncClient, db: AsyncSession) -> None:
    respondent = await make_respondent(db)
    before = await count_audit(db)

    url = f"/respondents/{respondent.respondent_id}/flag"
    first = await client.post(url, json={"flagged": True, "reason": "huella compartida"})
    again = await client.post(url, json={"flagged": True, "reason": "otra vez"})

    assert first.status_code == 200 and first.json()["is_flagged"] is True
    assert again.json()["changed"] is False
    await db.refresh(respondent)
    assert respondent.is_flagged
    rows = (await audit_rows(db, "flag_respondent"))[-1:]
    assert await count_audit(db) == before + 1
    assert rows[0].payload == {
        "respondent_id": str(respondent.respondent_id),
        "flagged": True,
        "previous": False,
        "reason": "huella compartida",
    }


async def test_flag_requires_a_reason(client: AsyncClient, db: AsyncSession) -> None:
    respondent = await make_respondent(db)
    response = await client.post(
        f"/respondents/{respondent.respondent_id}/flag", json={"flagged": True, "reason": ""}
    )
    assert response.status_code == 422


async def test_flag_unknown_respondent_is_404(client: AsyncClient) -> None:
    response = await client.post(
        f"/respondents/{uuid.uuid4()}/flag", json={"flagged": True, "reason": "x"}
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------------- pool


async def test_pool_tier_audits_only_what_changed(
    client: AsyncClient, db: AsyncSession, patch: Patch
) -> None:
    first, second = await make_champions(db, patch, 2, tier=3)
    await db.execute(
        sa.update(Champion).where(Champion.champion_id == second.champion_id).values(pool_tier=1)
    )
    await db.commit()

    response = await client.patch(
        "/champions/pool-tier",
        json={"champion_ids": [first.champion_id, second.champion_id], "pool_tier": 1},
    )
    noop = await client.patch(
        "/champions/pool-tier", json={"champion_ids": [first.champion_id], "pool_tier": 1}
    )

    assert response.json() == {"updated": 1}
    assert noop.json() == {"updated": 0}
    rows = await audit_rows(db, "set_pool_tier")
    assert rows[-1].payload == {
        "champion_ids": [first.champion_id],
        "pool_tier": 1,
        "updated": 1,
    }
    listing = (await client.get("/champions")).json()
    tiers = {c["champion_id"]: c["pool_tier"] for c in listing["champions"]}
    assert tiers[first.champion_id] == 1


async def test_pool_tier_rejects_bad_tier_and_unknown_ids(
    client: AsyncClient, db: AsyncSession, patch: Patch
) -> None:
    (champion,) = await make_champions(db, patch, 1)
    bad_tier = await client.patch(
        "/champions/pool-tier", json={"champion_ids": [champion.champion_id], "pool_tier": 4}
    )
    unknown = await client.patch(
        "/champions/pool-tier", json={"champion_ids": [999_999_999], "pool_tier": 2}
    )
    assert bad_tier.status_code == 400
    assert unknown.status_code == 404


# ---------------------------------------------------------------------------- parámetros


async def test_enabled_tiers_has_its_own_action(client: AsyncClient, db: AsyncSession) -> None:
    await set_setting(db, "sampler.enabled_pool_tiers", 1)
    response = await client.patch("/settings/sampler.enabled_pool_tiers", json={"value": 2})
    assert response.json() == {
        "key": "sampler.enabled_pool_tiers",
        "value": 2,
        "previous": 1,
        "changed": True,
    }
    rows = await audit_rows(db, "set_enabled_tiers")
    assert rows[-1].payload == {"key": "sampler.enabled_pool_tiers", "value": 2, "previous": 1}


async def test_a_value_of_the_same_shape_is_accepted(client: AsyncClient, db: AsyncSession) -> None:
    """24 §3.6: sin esquema por clave, pero con la forma del valor actual."""
    await set_setting(db, "sampler.epsilon", 1.0)
    response = await client.patch("/settings/sampler.epsilon", json={"value": 0})
    assert response.status_code == 200
    listing = (await client.get("/settings")).json()["settings"]
    stored = next(s for s in listing if s["key"] == "sampler.epsilon")
    assert stored["value"] == 0
    assert stored["updated_by"] == "admin"
    assert (await audit_rows(db, "set_setting"))[-1].payload["previous"] == 1.0


@pytest.mark.parametrize(
    ("current", "value"),
    [
        (5, "x"),  # el caso del 13/11: tiró `GET /questions/next`
        (5, True),
        (5, None),
        (5, [5]),
        ("America/Argentina/Buenos_Aires", 3),
        ([10, 15], ["a", "b"]),
        ({"retest": 0.4, "honeypot": 0.6}, {"retest": 0.4}),
        ({"retest": 0.4, "honeypot": 0.6}, {"retest": 0.4, "honeypot": "mucho"}),
    ],
)
async def test_a_value_of_another_shape_is_rejected(
    client: AsyncClient, db: AsyncSession, current: Any, value: Any
) -> None:
    await set_setting(db, "sampler.epsilon", current)
    before = await count_audit(db)
    response = await client.patch("/settings/sampler.epsilon", json={"value": value})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_parameter"
    listing = (await client.get("/settings")).json()["settings"]
    assert next(s for s in listing if s["key"] == "sampler.epsilon")["value"] == current
    assert await count_audit(db) == before


async def test_same_value_does_not_audit(client: AsyncClient, db: AsyncSession) -> None:
    await set_setting(db, "sampler.epsilon", 0.2)
    before = await count_audit(db)
    response = await client.patch("/settings/sampler.epsilon", json={"value": 0.2})
    assert response.json()["changed"] is False
    assert await count_audit(db) == before


async def test_unknown_key_is_not_created(client: AsyncClient) -> None:
    response = await client.patch("/settings/sampler.no_existe", json={"value": 1})
    assert response.status_code == 404


async def test_three_actions_three_rows(
    client: AsyncClient, db: AsyncSession, patch: Patch
) -> None:
    """CA-604 desde el panel: activar, promover y cambiar un parámetro dejan tres filas."""
    from tests.test_jobs_and_seeds import ready_patch

    await set_setting(db, "sampler.epsilon", 1.0)
    (champion,) = await make_champions(db, patch, 1, tier=2)
    new = await ready_patch(db, "99.98")
    before = await count_audit(db)

    await client.post(f"/patches/{new.version}/activate", json={})
    await client.patch(
        "/champions/pool-tier", json={"champion_ids": [champion.champion_id], "pool_tier": 1}
    )
    await client.patch("/settings/sampler.epsilon", json={"value": 0.5})

    rows = (await audit_rows(db))[before:]
    assert [r.action for r in rows] == ["activate_patch", "set_pool_tier", "set_setting"]


# -------------------------------------------------------------------------------- parches


async def test_activate_without_honeypots_is_409_and_not_audited(
    client: AsyncClient, db: AsyncSession, patch: Patch
) -> None:
    """CA-609: el panel usa las reglas de ADR-024 tal cual."""
    db.add(Patch(version="99.97", released_at=patch.released_at, is_current=False))
    await db.commit()
    before = await count_audit(db)

    refused = await client.post("/patches/99.97/activate", json={})
    assert refused.status_code == 409
    body = refused.json()["error"]
    assert body["code"] == "patch_not_ready"
    assert len(body["details"]) == 2
    assert await count_audit(db) == before
    await db.refresh(patch)
    assert patch.is_current

    forced = await client.post("/patches/99.97/activate", json={"force": True})
    assert forced.status_code == 200
    assert forced.json()["previous"] == "99.99"
    assert (await audit_rows(db, "activate_patch"))[-1].payload["version"] == "99.97"


async def test_activate_unknown_patch_is_404(client: AsyncClient) -> None:
    response = await client.post("/patches/0.0/activate", json={})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "patch_not_found"


async def test_unknown_body_field_is_rejected(client: AsyncClient, patch: Patch) -> None:
    """`forse` en vez de `force` no puede activar sin forzar en silencio."""
    response = await client.post(f"/patches/{patch.version}/activate", json={"forse": True})
    assert response.status_code == 422


async def test_patch_list_shows_what_is_missing(
    client: AsyncClient, db: AsyncSession, patch: Patch
) -> None:
    listing = (await client.get("/patches")).json()["patches"]
    current = next(p for p in listing if p["version"] == patch.version)
    assert current["is_current"] is True
    assert current["has_snapshot"] is False
    assert current["active_honeypots"] == 0
    assert len(current["missing"]) == 2


# ---------------------------------------------------------------------------- auditoría


async def test_audit_is_paginated_newest_first(
    client: AsyncClient, db: AsyncSession
) -> None:
    for epsilon in range(55):
        db.add(AdminAudit(action="set_setting", payload={"n": epsilon}))
    await db.commit()

    first = (await client.get("/audit", params={"action": "set_setting"})).json()
    second = (await client.get("/audit", params={"action": "set_setting", "page": 2})).json()
    assert first["page_size"] == 50
    assert len(first["items"]) == 50
    assert first["total"] >= 55
    assert first["items"][0]["audit_id"] > first["items"][-1]["audit_id"]
    assert second["items"]


async def test_respondent_trust_never_leaves(
    client: AsyncClient, db: AsyncSession
) -> None:
    """El panel muestra la distribución del trust, nunca el de alguien (22 §7)."""
    respondent = await make_respondent(db)
    respondent.is_flagged = True
    await db.commit()
    body = (await client.get("/quality")).json()
    wanted = str(respondent.respondent_id)
    flagged = next(f for f in body["flagged"] if f["respondent_id"] == wanted)
    assert "trust_score" not in flagged
    assert not any(isinstance(v, float) for v in flagged.values())
