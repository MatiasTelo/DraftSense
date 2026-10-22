"""Dependencias de FastAPI y la traducción de los errores del dominio al contrato (24 §5)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import patches, seeding
from draftsense_admin.config import AdminSettings, get_admin_settings
from draftsense_admin.db import get_session
from draftsense_admin.errors import AdminError
from draftsense_admin.services import actions, jobs, seeds

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[AdminSettings, Depends(get_admin_settings)]


def get_runner(request: Request) -> jobs.JobRunner:
    """El runner vive en `app.state`: tiene que ser uno solo por proceso, o el candado de «un job
    no corre dos veces a la vez» no protegería nada."""
    runner: jobs.JobRunner = request.app.state.job_runner
    return runner


RunnerDep = Annotated[jobs.JobRunner, Depends(get_runner)]


@contextmanager
def domain_errors() -> Iterator[None]:
    """Los errores de los services, en el sobre del contrato.

    El orden de los `except` importa: `PatchActivationError` y `SeedFileError` son subclases de
    `ValueError`, y si el genérico fuera primero se tragaría los dos como un 400 sin detalle.
    """
    try:
        yield
    except patches.PatchNotFoundError as exc:
        raise AdminError(
            "patch_not_found", str(exc), status.HTTP_404_NOT_FOUND, details=exc.problems
        ) from exc
    except patches.PatchActivationError as exc:
        raise AdminError(
            "patch_not_ready",
            "al parche le falta algo para servirse; se puede forzar",
            status.HTTP_409_CONFLICT,
            details=exc.problems,
        ) from exc
    except seeding.SeedFileError as exc:
        raise AdminError(
            "seed_invalid",
            f"{exc.path.name} no pasa la validación",
            422,
            details=exc.problems,
        ) from exc
    except seeds.SeedFileNotAllowedError as exc:
        raise AdminError(
            "invalid_parameter", str(exc), status.HTTP_400_BAD_REQUEST, field="file"
        ) from exc
    except jobs.UnknownJobError as exc:
        raise AdminError(
            "job_not_found", f"no existe el job {exc}", status.HTTP_404_NOT_FOUND
        ) from exc
    except jobs.JobRunningError as exc:
        raise AdminError(
            "job_running", f"el job {exc} ya está corriendo", status.HTTP_409_CONFLICT
        ) from exc
    except actions.NotFoundError as exc:
        raise AdminError("not_found", str(exc), status.HTTP_404_NOT_FOUND) from exc
    except ValueError as exc:
        raise AdminError("invalid_parameter", str(exc), status.HTTP_400_BAD_REQUEST) from exc
