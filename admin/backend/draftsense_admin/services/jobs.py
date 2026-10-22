"""Los cuatro jobs de fondo, disparados a mano desde el panel (`docs/24-panel-admin.md` §3.7).

Corren **en segundo plano**, en una tarea de este proceso: el pedido vuelve enseguida con un
`run_id` y la vista consulta el estado. Cada corrida abre su propia sesión, porque la del request
se cierra cuando el request termina y el job sigue.

El estado vive en memoria y se guarda sólo la última corrida de cada job. Si el proceso se
reinicia, el job en curso se corta con él y no queda auditado: la auditoría se escribe al terminar
bien, con el resultado. La programación periódica sigue pendiente con el despliegue.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import connectivity, degenerate, fingerprints, question_stats
from draftsense_admin.services import audit

Status = Literal["running", "succeeded", "failed"]
SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
Runner = Callable[[AsyncSession, dict[str, Any]], Awaitable[object]]

#: La ventana por defecto de `detect_degenerate_patterns`, la misma que el CLI.
DEFAULT_SINCE_HOURS: Final = 24


def _since_hours(params: dict[str, Any]) -> int:
    value = params.get("since_hours", DEFAULT_SINCE_HOURS)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("since_hours tiene que ser un entero positivo")
    return value


async def _refresh(session: AsyncSession, _: dict[str, Any]) -> object:
    return await question_stats.refresh(session)


async def _connectivity(session: AsyncSession, _: dict[str, Any]) -> object:
    result = await connectivity.check(session)
    # `connected` es una propiedad: `plain` sólo ve los campos del dataclass.
    return {**audit.plain(result), "connected": result.connected}


async def _degenerate(session: AsyncSession, params: dict[str, Any]) -> object:
    return await degenerate.detect(session, since_hours=_since_hours(params))


async def _fingerprints(session: AsyncSession, _: dict[str, Any]) -> object:
    return await fingerprints.flag_duplicates(session)


@dataclass(frozen=True, slots=True)
class Job:
    name: str
    label: str
    runner: Runner
    validate: Callable[[dict[str, Any]], dict[str, Any]] = lambda params: {}


JOBS: Final = {
    job.name: job
    for job in (
        Job(
            "refresh_question_stats",
            "Recalcular estadísticas de preguntas",
            _refresh,
        ),
        Job(
            "check_graph_connectivity",
            "Chequear conectividad del grafo",
            _connectivity,
        ),
        Job(
            "detect_degenerate_patterns",
            "Detectar patrones degenerados",
            _degenerate,
            lambda params: {"since_hours": _since_hours(params)},
        ),
        Job(
            "flag_duplicate_fingerprints",
            "Marcar huellas duplicadas",
            _fingerprints,
        ),
    )
}


class UnknownJobError(LookupError):
    pass


class JobRunningError(RuntimeError):
    pass


@dataclass(slots=True)
class Run:
    run_id: str
    job: str
    params: dict[str, Any]
    status: Status = "running"
    started_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    finished_at: dt.datetime | None = None
    result: Any = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "job": self.job,
            "params": self.params,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
        }


class JobRunner:
    """Una corrida a la vez por job; los cuatro pueden correr en paralelo entre sí."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions
        self._last: dict[str, Run] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def last(self, job: str) -> Run | None:
        return self._last.get(job)

    def get(self, job: str, run_id: str) -> Run | None:
        run = self._last.get(job)
        return run if run is not None and run.run_id == run_id else None

    def start(self, name: str, params: dict[str, Any]) -> Run:
        job = JOBS.get(name)
        if job is None:
            raise UnknownJobError(name)
        current = self._last.get(name)
        if current is not None and current.status == "running":
            raise JobRunningError(name)
        clean = job.validate(params)
        run = Run(run_id=uuid.uuid4().hex, job=name, params=clean)
        self._last[name] = run
        # Se guarda la referencia: una tarea sin referencias la puede recolectar el GC a mitad
        # de camino (advertencia de la documentación de `asyncio.create_task`).
        self._tasks[name] = asyncio.create_task(self._execute(job, run))
        return run

    async def wait(self, name: str) -> None:
        """Espera a que termine la corrida en curso. Para los tests y para cerrar el proceso."""
        task = self._tasks.get(name)
        if task is not None:
            await task

    async def _execute(self, job: Job, run: Run) -> None:
        try:
            async with self._sessions() as session:
                result = audit.plain(await job.runner(session, run.params))
                audit.record(
                    session, "run_job", {"job": job.name, "params": run.params, "result": result}
                )
                await session.commit()
        except Exception as exc:  # el error se muestra en el panel; no hay a quién propagarlo
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
        else:
            run.status = "succeeded"
            run.result = result
        finally:
            run.finished_at = dt.datetime.now(dt.UTC)
