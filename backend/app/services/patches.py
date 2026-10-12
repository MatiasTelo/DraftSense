"""Registrar un parche y activarlo, que son dos pasos distintos (ADR-024).

Hasta la semana 6 los seeds activaban el parche como efecto lateral: el primer `seed-champions`
dejaba vigente un parche sin snapshot ni honeypots, y el sampler empezaba a servir preguntas contra
él. Ahora los seeds sólo registran (`register`) y el parche cambia únicamente con `activate`, que
usan el comando `activate-patch` y, desde la semana 7, `POST /admin/patches/{patch_id}/activate`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAudit, Patch, PickRateSnapshot
from app.services import honeypots


class PatchActivationError(ValueError):
    """El parche no existe, o le falta algo para poder servirse y no se forzó."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


class PatchNotFoundError(PatchActivationError):
    """El parche no está registrado: falta correr `seed-champions` contra él."""


@dataclass(frozen=True, slots=True)
class ActivationResult:
    """La forma de la respuesta de `12-api.md` §2, que es también el payload de la auditoría."""

    patch_id: int
    version: str
    previous: str | None
    #: `False` si el parche ya era el vigente: no se tocó nada ni se auditó.
    changed: bool


async def register(
    session: AsyncSession, version: str, released_at: dt.date | None = None
) -> Patch:
    """Devuelve el parche pedido, creándolo si no existe. **No lo activa.**

    `released_at` es NOT NULL y no se puede deducir de Data Dragon, que sólo publica la versión.
    Sin fecha se usa la de hoy, que es aproximada: el parche se siembra días después de salir.
    Pasarla explícitamente es lo correcto cuando se la conoce.
    """
    patch = (
        await session.execute(sa.select(Patch).where(Patch.version == version))
    ).scalar_one_or_none()
    if patch is None:
        patch = Patch(
            version=version, released_at=released_at or dt.date.today(), is_current=False
        )
        session.add(patch)
    elif released_at is not None:
        patch.released_at = released_at
    await session.commit()
    return patch


async def missing_for(session: AsyncSession, patch: Patch) -> list[str]:
    """Lo que le falta al parche para servirse bien.

    Sin snapshot de pick rate, el pool y los roles no corresponden al parche (ADR-006, ADR-019).
    Sin honeypots activas nadie suma intentos y el trust queda congelado en el valor inicial
    durante todo el parche, sin que ninguna pantalla lo muestre.
    """
    problems: list[str] = []
    snapshots = (
        await session.execute(
            sa.select(sa.func.count())
            .select_from(PickRateSnapshot)
            .where(PickRateSnapshot.patch_id == patch.patch_id)
        )
    ).scalar_one()
    if not snapshots:
        problems.append(f"el parche {patch.version} no tiene snapshot de pick rate")
    if not await honeypots.catalog(session, patch.patch_id):
        problems.append(f"el parche {patch.version} no tiene honeypots activas")
    return problems


async def activate(session: AsyncSession, version: str, force: bool = False) -> ActivationResult:
    """Marca el parche como vigente y lo audita, en una sola transacción.

    Lo que ya está en vuelo no se toca: las preguntas y respuestas anteriores conservan su
    `patch_id`, y el sampler descarta solo la honeypot y el retest pendientes de otro parche
    (`docs/21-sampler.md` §8, nota del 11/10).
    """
    patch = (
        await session.execute(sa.select(Patch).where(Patch.version == version))
    ).scalar_one_or_none()
    if patch is None:
        raise PatchNotFoundError([f"no existe el parche {version}"])

    current = (
        await session.execute(sa.select(Patch).where(Patch.is_current))
    ).scalar_one_or_none()
    previous = current.version if current is not None else None
    if current is not None and current.patch_id == patch.patch_id:
        # Repetir el comando no debe llenar `admin_audit` de filas sin cambio.
        return ActivationResult(patch.patch_id, patch.version, previous, changed=False)

    problems = await missing_for(session, patch)
    if problems and not force:
        raise PatchActivationError(problems)

    # El índice único parcial `patches_single_current` sólo admite un vigente a la vez, así que
    # hay que bajar el anterior antes de subir el nuevo.
    await session.execute(sa.update(Patch).values(is_current=False))
    await session.execute(
        sa.update(Patch).where(Patch.patch_id == patch.patch_id).values(is_current=True)
    )
    result = ActivationResult(patch.patch_id, patch.version, previous, changed=True)
    session.add(
        AdminAudit(
            action="activate_patch",
            payload={
                "patch_id": result.patch_id,
                "version": result.version,
                "previous": result.previous,
            },
        )
    )
    await session.commit()
    return result
