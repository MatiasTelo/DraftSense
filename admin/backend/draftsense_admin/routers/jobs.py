"""Los cuatro jobs, en segundo plano (24 §3.7)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status

from draftsense_admin.dependencies import RunnerDep, SessionDep, domain_errors
from draftsense_admin.errors import AdminError
from draftsense_admin.schemas import JobIn
from draftsense_admin.services import audit, jobs

router = APIRouter(tags=["jobs"])


@router.get("/jobs")
async def list_jobs(session: SessionDep, runner: RunnerDep) -> dict[str, Any]:
    audited = await audit.last_by_job(session)
    return {
        "jobs": [
            {
                "job": job.name,
                "label": job.label,
                "last_run": run.as_dict() if (run := runner.last(job.name)) else None,
                "last_audited_at": audited.get(job.name),
            }
            for job in jobs.JOBS.values()
        ]
    }


@router.post("/jobs/{job}", status_code=status.HTTP_202_ACCEPTED)
async def start(job: str, body: JobIn, runner: RunnerDep) -> dict[str, Any]:
    with domain_errors():
        run = runner.start(job, body.params)
    return {"run_id": run.run_id, "job": run.job, "status": run.status}


@router.get("/jobs/{job}/runs/{run_id}")
async def get_run(job: str, run_id: str, runner: RunnerDep) -> dict[str, Any]:
    run = runner.get(job, run_id)
    if run is None:
        raise AdminError(
            "run_not_found", "esa corrida no existe o ya no es la última", status.HTTP_404_NOT_FOUND
        )
    return run.as_dict()
