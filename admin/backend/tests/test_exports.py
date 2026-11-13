"""*Generar CSV* desde el panel — CA-612 de `docs/24-panel-admin.md` §7 (nota del 29/10)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAudit, Export, Patch, Question, QuestionType
from draftsense_admin.services.exporting import ExportRunner
from tests.conftest import (
    add_response,
    make_champions,
    make_dimensions,
    make_respondent,
    pairwise_question,
    requires_db,
    restrict_pool,
)

pytestmark = requires_db


async def _data(db: AsyncSession, patch: Patch) -> None:
    champions = await make_champions(db, patch, 3, prefix="Ex")
    [dimension] = await make_dimensions(db, ["exdim"])
    await restrict_pool(db, champions, [dimension])
    people = [await make_respondent(db, f"fp-export-{i}") for i in range(3)]
    for person in people:
        for first, second in ((0, 1), (1, 2), (0, 2)):
            question = (
                await pairwise_question(db, patch, champions[first], champions[second], dimension)
                if person is people[0]
                else (
                    await db.execute(
                        sa.select(Question).where(
                            Question.champion_a
                            == min(champions[first].champion_id, champions[second].champion_id),
                            Question.champion_b
                            == max(champions[first].champion_id, champions[second].champion_id),
                            Question.dimension_id == dimension.dimension_id,
                        )
                    )
                ).scalar_one()
            )
            await add_response(db, person, question, {"choice": "a"})
    peak = Question(
        type=QuestionType.PEAK_TIMING,
        champion_a=champions[0].champion_id,
        patch_id=patch.patch_id,
    )
    db.add(peak)
    await db.commit()
    for person in people:
        await add_response(db, person, peak, {"minute": 18})


def _runner(app: FastAPI) -> ExportRunner:
    runner: ExportRunner = app.state.export_runner
    return runner


async def test_ca612_generar_csv_corre_registra_audita_y_descarga(
    client: AsyncClient, admin_app: FastAPI, db: AsyncSession, patch: Patch, tmp_path: Path
) -> None:
    await _data(db, patch)
    listed = (await client.get("/exports")).json()
    assert listed["enabled"] is True

    started = await client.post("/exports", json={"bootstrap": 20})
    assert started.status_code == 202
    # Mientras corre, una segunda exportación es 409.
    again = await client.post("/exports", json={"bootstrap": 20})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "export_running"
    await _runner(admin_app).wait()

    run = (await client.get(f"/exports/runs/{started.json()['run_id']}")).json()
    assert run["status"] == "succeeded", run["error"]
    files = run["result"]["files"]
    # Los seis CSV y el Informe de Calidad de Datos (27 §9.1).
    assert len(files) == 7
    assert files[-1]["file_name"].startswith("data_quality_report_v")

    rows = list(
        (
            await db.execute(
                sa.select(Export).where(Export.export_id.in_([f["export_id"] for f in files]))
            )
        ).scalars()
    )
    assert all(r.params["bootstrap_samples"] == 20 for r in rows)
    # Se busca la fila de esta corrida por sus archivos: la base puede tener exportaciones
    # auditadas de antes, por ejemplo las del panel en una prueba manual.
    hashes = [f["sha256"] for f in files]
    audited = [
        row
        for row in (
            await db.execute(sa.select(AdminAudit).where(AdminAudit.action == "trigger_export"))
        ).scalars()
        if [f["sha256"] for f in row.payload["files"]] == hashes
    ]
    assert len(audited) == 1

    first = files[0]
    download = await client.get(f"/exports/{first['export_id']}/file")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/csv")
    assert hashlib.sha256(download.content).hexdigest() == first["sha256"]
    report = await client.get(f"/exports/{files[-1]['export_id']}/file")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/markdown")
    assert hashlib.sha256(report.content).hexdigest() == files[-1]["sha256"]

    listed = (await client.get("/exports")).json()
    assert {e["run"] for e in listed["exports"] if e["export_id"] == first["export_id"]} != {None}


async def test_una_corrida_sin_datos_falla_sin_auditar(
    client: AsyncClient, admin_app: FastAPI, db: AsyncSession, patch: Patch
) -> None:
    champions = await make_champions(db, patch, 2, prefix="Ey")
    await restrict_pool(db, champions, await make_dimensions(db, ["eydim"]))
    count = (
        sa.select(sa.func.count())
        .select_from(AdminAudit)
        .where(AdminAudit.action == "trigger_export")
    )
    before = (await db.execute(count)).scalar_one()
    started = await client.post("/exports", json={"bootstrap": 20})
    await _runner(admin_app).wait()
    run = (await client.get(f"/exports/runs/{started.json()['run_id']}")).json()
    assert run["status"] == "failed"
    assert "ninguna respuesta" in run["error"]
    assert (await db.execute(count)).scalar_one() == before


async def test_los_parametros_se_validan(client: AsyncClient) -> None:
    assert (await client.post("/exports", json={"bootstrap": 0})).status_code == 400
    assert (await client.post("/exports", json={"min_trust": 3})).status_code == 400
    assert (await client.post("/exports", json={"patch_window": ".."})).status_code == 400
    # 13/11/2026: con vida media 0 la corrida arrancaba y moría con `ZeroDivisionError`.
    assert (await client.post("/exports", json={"halflife": 0})).status_code == 400
    assert (await client.post("/exports", json={"min_trust": 0})).status_code == 400


async def test_dos_corridas_del_mismo_dia_no_se_pisan(
    client: AsyncClient, admin_app: FastAPI, db: AsyncSession, patch: Patch
) -> None:
    """Cada corrida tiene su carpeta: la segunda no deja sin descarga a la primera.

    Hasta el 13/11/2026 la carpeta salía de la ventana, la fecha y la semilla, que no cambian
    entre dos corridas del mismo día con los mismos cuatro campos del formulario. Entre una y
    otra entra una respuesta, los archivos cambian, y el SHA-256 de la primera dejaba de coincidir.
    """
    await _data(db, patch)

    async def run() -> list[dict[str, Any]]:
        started = await client.post("/exports", json={"bootstrap": 20})
        await _runner(admin_app).wait()
        status = (await client.get(f"/exports/runs/{started.json()['run_id']}")).json()
        assert status["status"] == "succeeded", status["error"]
        files: list[dict[str, Any]] = status["result"]["files"]
        return files

    first = await run()
    peak = (
        await db.execute(
            sa.select(Question).where(
                Question.type == QuestionType.PEAK_TIMING,
                Question.patch_id == patch.patch_id,
            )
        )
    ).scalar_one()
    # Cuatro contra tres: la mediana del pico se mueve y el archivo cambia.
    for i in range(4):
        person = await make_respondent(db, f"fp-export-extra-{i}")
        await add_response(db, person, peak, {"minute": 35})
    second = await run()

    assert [f["sha256"] for f in first] != [f["sha256"] for f in second]
    for file in (*first, *second):
        download = await client.get(f"/exports/{file['export_id']}/file")
        assert download.status_code == 200, file["file_name"]
        assert hashlib.sha256(download.content).hexdigest() == file["sha256"]


async def test_un_export_inexistente_es_404(client: AsyncClient) -> None:
    response = await client.get("/exports/999999999/file")
    assert response.status_code == 404
