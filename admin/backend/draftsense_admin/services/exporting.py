"""*Generar CSV* desde el panel (`docs/24-panel-admin.md` §3.9, nota del 29/10).

Corre el mismo `aggregation.pipeline.run` que la línea de comandos, **en segundo plano** como los
jobs: el pedido vuelve con un `run_id`, la vista consulta el estado, y una segunda corrida mientras
hay una en curso es `409 export_running`. La auditoría (`trigger_export`) se escribe al terminar
bien; una corrida que falla —ninguna respuesta pasa los filtros, por ejemplo— no escribe nada y no
audita.

Cada corrida escribe en su propia carpeta de `DS_EXPORTS_DIR`, nombrada por la ventana, la fecha
de exportación, la semilla **y el id de la corrida**. Hasta el 13/11/2026 faltaba lo último, con
el argumento de que dos corridas iguales dan los mismos archivos; pero la semilla no lleva todos
los parámetros ni el estado del crudo, así que dos corridas del mismo día caían en la misma
carpeta, la segunda pisaba a la primera y sus filas de `exports` dejaban de poder descargarse
(el SHA-256 ya no coincidía). La descarga busca el archivo por `export_id`: lee la fila de
`exports`, toma la carpeta de sus `params` y verifica el SHA-256 antes de devolverlo.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from aggregation import params as run_params
from aggregation import pipeline
from aggregation.load import NoDataError
from app.models import Export
from app.services import questions
from draftsense_admin.services import audit
from draftsense_admin.services.jobs import SessionFactory, Status


class ExportRunningError(RuntimeError):
    pass


class ExportFileMissingError(LookupError):
    pass


def legacy_folder_name(record: dict[str, Any]) -> str | None:
    """La carpeta de una corrida anterior al 13/11/2026, que no guardaba `folder`."""
    try:
        return f"{record['patch_window']}_{record['exported_at']}_{record['seed']}"
    except KeyError:
        return None


def folder_name(record: dict[str, Any]) -> str | None:
    """La carpeta de una corrida, a partir de lo registrado en `exports.params`."""
    folder = record.get("folder")
    return str(folder) if folder else legacy_folder_name(record)


def _number(params: dict[str, Any], key: str, kind: type) -> Any:
    value = params.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{key} tiene que ser un número")
    if kind is int and (not float(value).is_integer() or value < 1):
        raise ValueError(f"{key} tiene que ser un entero positivo")
    if kind is float and value <= 0:
        raise ValueError(f"{key} tiene que ser mayor que 0")
    return kind(value)


def validate(params: dict[str, Any]) -> dict[str, Any]:
    """Los cuatro campos del formulario de CU-08. Los que faltan salen de `app_settings`."""
    unknown = set(params) - {"patch_window", "min_trust", "halflife", "bootstrap"}
    if unknown:
        raise ValueError(f"parámetros desconocidos: {', '.join(sorted(unknown))}")
    window = params.get("patch_window")
    if window is not None:
        if not isinstance(window, str):
            raise ValueError("patch_window tiene que ser texto, como 16.18..16.20")
        run_params.parse_window(window)
    trust = _number(params, "min_trust", float)
    if trust is not None and trust > 1:
        raise ValueError("min_trust va entre 0 y 1, sin el 0")
    return {
        "patch_window": window,
        "min_trust": trust,
        "halflife": _number(params, "halflife", float),
        "bootstrap": _number(params, "bootstrap", int),
    }


@dataclass(slots=True)
class ExportRun:
    run_id: str
    params: dict[str, Any]
    status: Status = "running"
    started_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    finished_at: dt.datetime | None = None
    result: Any = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "params": self.params,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
        }


class ExportRunner:
    """Una exportación a la vez: el bootstrap de los 15 ajustes ya usa todos los procesadores."""

    def __init__(
        self, sessions: SessionFactory, out_dir: Path, workers: int | None = None
    ) -> None:
        self._sessions = sessions
        self._out_dir = out_dir
        self._workers = workers
        self._last: ExportRun | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def out_dir(self) -> Path:
        """La carpeta de exportaciones. La descarga lee de la misma en la que se escribió."""
        return self._out_dir

    def get(self, run_id: str) -> ExportRun | None:
        return self._last if self._last is not None and self._last.run_id == run_id else None

    def last(self) -> ExportRun | None:
        return self._last

    def start(self, params: dict[str, Any]) -> ExportRun:
        if self._last is not None and self._last.status == "running":
            raise ExportRunningError()
        run = ExportRun(run_id=uuid.uuid4().hex, params=validate(params))
        self._last = run
        self._task = asyncio.create_task(self._execute(run))
        return run

    async def wait(self) -> None:
        if self._task is not None:
            await self._task

    async def _execute(self, run: ExportRun) -> None:
        try:
            async with self._sessions() as session:
                result = await self._run(session, run)
        except (NoDataError, ValueError) as exc:
            run.status = "failed"
            run.error = str(exc)
        except Exception as exc:  # el error se muestra en el panel; no hay a quién propagarlo
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
        else:
            run.status = "succeeded"
            run.result = result
        finally:
            run.finished_at = dt.datetime.now(dt.UTC)

    async def _run(self, session: AsyncSession, run: ExportRun) -> dict[str, Any]:
        form = run.params
        patch = await questions.current_patch(session)
        resolved = await run_params.resolve(
            session,
            patch_window=form["patch_window"],
            current_patch=patch.version if patch is not None else None,
            min_trust=form["min_trust"],
            halflife=form["halflife"],
            bootstrap=form["bootstrap"],
        )
        record = resolved.as_record()
        # El id de la corrida hace única la carpeta: ver el docstring del módulo.
        folder = self._out_dir / f"{legacy_folder_name(record)}_{run.run_id[:8]}"
        result = await pipeline.run(session, resolved, folder, workers=self._workers)
        files = [
            {
                "export_id": export_id,
                "file_name": f.file_name,
                "sha256": f.sha256,
                "row_count": f.rows,
            }
            for export_id, f in zip(result.export_ids, result.files, strict=True)
        ]
        payload = {"params": record, "files": files}
        audit.record(session, "trigger_export", payload)
        await session.commit()
        return {
            **payload,
            "responses": result.responses,
            "respondents": result.respondents,
            "warnings": [
                report.name for report in result.reports if report.failed or report.components > 1
            ],
        }


async def file_for(session: AsyncSession, out_dir: Path, export_id: int) -> tuple[Path, str]:
    """El archivo de una fila de `exports`, verificado contra su SHA-256."""
    row = await session.get(Export, export_id)
    if row is None:
        raise ExportFileMissingError(f"no existe la exportación {export_id}")
    record = row.params or {}
    # Una corrida del CLI guarda como `folder` el nombre de su `--out`, que puede no estar bajo
    # la carpeta del panel: se prueba también el nombre viejo antes de darla por perdida.
    names = dict.fromkeys(n for n in (folder_name(record), legacy_folder_name(record)) if n)
    path = next(
        (p for p in (out_dir / name / row.file_name for name in names) if p.is_file()), None
    )
    if path is None:
        raise ExportFileMissingError(f"{row.file_name} no está en la carpeta de exportaciones")
    if hashlib.sha256(path.read_bytes()).hexdigest() != row.sha256:
        raise ExportFileMissingError(f"{row.file_name} no coincide con el SHA-256 registrado")
    return path, row.file_name
