"""Jobs en segundo plano y seeds desde el panel, los dos auditados (CA-610, 24 §3.7 y §3.8)."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAudit, Patch, PickRateSnapshot, Question
from draftsense_admin.config import AdminSettings, get_admin_settings
from draftsense_admin.services import jobs
from tests.conftest import (
    make_champions,
    make_dimensions,
    pairwise_question,
    requires_db,
    restrict_pool,
)

pytestmark = requires_db


async def ready_patch(db: AsyncSession, version: str) -> Patch:
    """Un parche no vigente con lo que pide ADR-024: snapshot de pick rate y una honeypot."""
    patch = Patch(version=version, released_at=dt.date(2026, 10, 1), is_current=False)
    db.add(patch)
    await db.commit()
    await db.refresh(patch)
    db.add(
        PickRateSnapshot(
            source="lolalytics",
            source_url="https://example.invalid/snapshot",
            captured_at=dt.date(2026, 10, 1),
            patch_id=patch.patch_id,
        )
    )
    await db.commit()
    first, second = await make_champions(db, patch, 2, prefix=f"Ready{version.replace('.', '')}")
    (dimension,) = await make_dimensions(db, ["admindim"])
    await pairwise_question(
        db, patch, first, second, dimension, is_honeypot=True, expected_answer={"choice": "a"}
    )
    return patch


async def last_audit(db: AsyncSession, action: str) -> AdminAudit:
    return (
        await db.execute(
            sa.select(AdminAudit)
            .where(AdminAudit.action == action)
            .order_by(AdminAudit.audit_id.desc())
            .limit(1)
        )
    ).scalar_one()


async def wait_for(client: AsyncClient, job: str, run_id: str) -> dict[str, Any]:
    for _ in range(200):
        run = (await client.get(f"/jobs/{job}/runs/{run_id}")).json()
        if run["status"] != "running":
            return run
        await asyncio.sleep(0.05)
    raise AssertionError(f"{job} no terminó")


# ------------------------------------------------------------------------------------- jobs


async def test_job_runs_in_background_and_is_audited(
    client: AsyncClient, db: AsyncSession, patch: Patch
) -> None:
    started = await client.post("/jobs/refresh_question_stats", json={})
    assert started.status_code == 202
    body = started.json()
    assert body["status"] == "running"

    run = await wait_for(client, "refresh_question_stats", body["run_id"])
    assert run["status"] == "succeeded", run["error"]
    assert run["result"]["patch"] == patch.version

    row = await last_audit(db, "run_job")
    assert row.payload["job"] == "refresh_question_stats"
    assert row.payload["result"]["patch"] == patch.version
    listing = (await client.get("/jobs")).json()["jobs"]
    entry = next(j for j in listing if j["job"] == "refresh_question_stats")
    assert entry["last_run"]["run_id"] == body["run_id"]
    assert entry["last_audited_at"] is not None


async def test_connectivity_job_reports_connected(
    client: AsyncClient, db: AsyncSession, patch: Patch
) -> None:
    started = (await client.post("/jobs/check_graph_connectivity", json={})).json()
    run = await wait_for(client, "check_graph_connectivity", started["run_id"])
    assert run["status"] == "succeeded", run["error"]
    assert "connected" in run["result"]


async def test_degenerate_job_validates_its_window(client: AsyncClient) -> None:
    bad = await client.post("/jobs/detect_degenerate_patterns", json={"params": {"since_hours": 0}})
    assert bad.status_code == 400
    ok = await client.post(
        "/jobs/detect_degenerate_patterns", json={"params": {"since_hours": 48}}
    )
    run = await wait_for(client, "detect_degenerate_patterns", ok.json()["run_id"])
    assert run["status"] == "succeeded", run["error"]
    assert run["params"] == {"since_hours": 48}


async def test_unknown_job_is_404(client: AsyncClient) -> None:
    response = await client.post("/jobs/borrar_todo", json={})
    assert response.status_code == 404


async def test_same_job_does_not_run_twice() -> None:
    """Mientras corre, un segundo pedido es `409 job_running`; los otros jobs sí arrancan."""
    gate = asyncio.Event()

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        await gate.wait()
        raise RuntimeError("sin base en este test")
        yield  # pragma: no cover

    runner = jobs.JobRunner(sessions)
    first = runner.start("flag_duplicate_fingerprints", {})
    with pytest.raises(jobs.JobRunningError):
        runner.start("flag_duplicate_fingerprints", {})
    other = runner.start("refresh_question_stats", {})
    gate.set()
    await runner.wait("flag_duplicate_fingerprints")
    await runner.wait("refresh_question_stats")

    assert first.status == "failed" and other.status == "failed"
    assert first.error is not None and "sin base" in first.error
    # Terminado, se puede volver a correr.
    assert runner.start("flag_duplicate_fingerprints", {}).status == "running"
    await runner.wait("flag_duplicate_fingerprints")


async def test_failed_job_is_not_audited(client: AsyncClient, db: AsyncSession) -> None:
    before = (
        await db.execute(sa.select(sa.func.count()).select_from(AdminAudit))
    ).scalar_one()

    async def boom(_: AsyncSession, __: dict[str, Any]) -> object:
        raise RuntimeError("falló a propósito")

    original = jobs.JOBS["flag_duplicate_fingerprints"]
    jobs.JOBS["flag_duplicate_fingerprints"] = jobs.Job(original.name, original.label, boom)
    try:
        started = (await client.post("/jobs/flag_duplicate_fingerprints", json={})).json()
        run = await wait_for(client, "flag_duplicate_fingerprints", started["run_id"])
    finally:
        jobs.JOBS["flag_duplicate_fingerprints"] = original
    assert run["status"] == "failed"
    assert "falló a propósito" in run["error"]
    after = (
        await db.execute(sa.select(sa.func.count()).select_from(AdminAudit))
    ).scalar_one()
    assert after == before


# ------------------------------------------------------------------------------------ seeds


@pytest.fixture
def seeds_dir(admin_app: FastAPI, tmp_path: Path) -> Path:
    """Un `infra/seeds/` de juguete, inyectado en la configuración del panel."""
    directory = tmp_path / "seeds"
    directory.mkdir()
    settings = AdminSettings(seeds_dir=directory)
    admin_app.dependency_overrides[get_admin_settings] = lambda: settings
    return directory


async def test_pick_rate_seed_is_audited(
    client: AsyncClient, db: AsyncSession, patch: Patch, seeds_dir: Path
) -> None:
    champions = await make_champions(db, patch, 2, prefix="Seed")
    (seeds_dir / "pick_rate_99.99.csv").write_text(
        "role,champion_name,pick_rate,rank_in_role\n"
        f"mid,{champions[0].display_name},0.1200,1\n"
        f"mid,{champions[1].display_name},0.0800,2\n",
        encoding="utf-8",
    )
    files = (await client.get("/seeds/files")).json()
    assert files["pick_rate"] == ["pick_rate_99.99.csv"]

    response = await client.post(
        "/seeds/pick-rate",
        json={
            "version": patch.version,
            "file": "pick_rate_99.99.csv",
            "source_url": "https://example.invalid/tierlist",
            "captured_at": "2026-10-20",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["loaded"] == 2

    row = await last_audit(db, "run_seed")
    assert row.payload["seed"] == "pick_rate"
    assert row.payload["patch"] == patch.version
    assert row.payload["file"] == "pick_rate_99.99.csv"
    assert row.payload["result"]["loaded"] == 2


async def test_invalid_seed_file_is_422_and_not_audited(
    client: AsyncClient, db: AsyncSession, patch: Patch, seeds_dir: Path
) -> None:
    (seeds_dir / "pick_rate_99.99.csv").write_text(
        "role,champion_name,pick_rate,rank_in_role\nmid,Nadie,1.5,2\n", encoding="utf-8"
    )
    before = (
        await db.execute(sa.select(sa.func.count()).select_from(AdminAudit))
    ).scalar_one()
    response = await client.post(
        "/seeds/pick-rate",
        json={
            "version": patch.version,
            "file": "pick_rate_99.99.csv",
            "source_url": "https://example.invalid/tierlist",
            "captured_at": "2026-10-20",
        },
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "seed_invalid"
    assert len(error["details"]) == 2
    after = (
        await db.execute(sa.select(sa.func.count()).select_from(AdminAudit))
    ).scalar_one()
    assert after == before


async def test_seed_outside_infra_seeds_is_400(
    client: AsyncClient, patch: Patch, seeds_dir: Path
) -> None:
    """CA-611."""
    response = await client.post(
        "/seeds/honeypots", json={"version": patch.version, "file": "../backend/.env"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["field"] == "file"


async def test_exports_form_defaults(client: AsyncClient, patch: Patch) -> None:
    """24 §3.9: desde la semana 9 el botón está habilitado y el formulario trae los valores de
    `app_settings`. La corrida completa es CA-612, en `test_exports.py`."""
    body = (await client.get("/exports")).json()
    assert body["enabled"] is True
    assert body["defaults"]["patch_window"] == patch.version


async def test_reading_connectivity_creates_nothing(
    client: AsyncClient, db: AsyncSession, patch: Patch
) -> None:
    """La vista calcula componentes sin marcar ni materializar puentes (24 §3.2, CA-608)."""
    champions = await make_champions(db, patch, 4, prefix="Graph")
    dimensions = await make_dimensions(db, ["graphone", "graphtwo"])
    await restrict_pool(db, champions, dimensions)
    count = sa.select(sa.func.count()).select_from(Question)
    before = (await db.execute(count)).scalar_one()
    await client.get("/connectivity")
    assert (await db.execute(count)).scalar_one() == before
