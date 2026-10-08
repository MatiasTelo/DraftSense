"""Deduplicación por huella — CA-306 de `03-criterios-aceptacion.md` §4.

Se cuenta la **creación** de identidades (`first_seen`), no la actividad, y se marcan todas las de
la huella. Ninguna respuesta se borra (22 §6.2).
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dimension, Patch, Respondent, Response
from app.services import fingerprints, sessions
from tests.conftest import add_response, make_champions, pairwise_question, requires_db


async def _identities(db: AsyncSession, fingerprint: str, count: int) -> list[Respondent]:
    return [(await sessions.create(db, fingerprint))[0] for _ in range(count)]


def _fingerprint() -> str:
    """Una huella que no comparte nadie más en la base, tampoco en staging."""
    return f"huella-{uuid.uuid4()}"


@requires_db
async def test_ca306_seis_identidades_en_24_horas_quedan_las_seis_marcadas(
    db: AsyncSession, patch: Patch, dimension: Dimension
) -> None:
    fingerprint = _fingerprint()
    identities = await _identities(db, fingerprint, 6)
    pool = await make_champions(db, patch, 2, prefix="Fp")
    question = await pairwise_question(db, patch, pool[0], pool[1], dimension)
    await add_response(db, identities[0], question, {"choice": "a"})

    result = await fingerprints.flag_duplicates(db)

    flags = (
        await db.execute(
            sa.select(Respondent.is_flagged).where(Respondent.fingerprint_hash == fingerprint)
        )
    ).scalars()
    assert list(flags) == [True] * 6
    assert result.flagged >= 6
    # Marcar no borra: la respuesta de la primera identidad sigue en el crudo.
    kept = (
        await db.execute(
            sa.select(sa.func.count())
            .select_from(Response)
            .where(Response.respondent_id == identities[0].respondent_id)
        )
    ).scalar_one()
    assert kept == 1


@requires_db
async def test_cinco_identidades_no_alcanzan(db: AsyncSession) -> None:
    """El umbral es «más de 5» (`quality.fingerprint_max_identities`)."""
    fingerprint = _fingerprint()
    await _identities(db, fingerprint, 5)

    await fingerprints.flag_duplicates(db)

    flags = (
        await db.execute(
            sa.select(Respondent.is_flagged).where(Respondent.fingerprint_hash == fingerprint)
        )
    ).scalars()
    assert not any(flags)


@requires_db
async def test_se_cuenta_por_creacion_y_no_por_actividad(db: AsyncSession) -> None:
    """Una PC compartida con identidades viejas no es el ataque que se busca (22 §6.2)."""
    fingerprint = _fingerprint()
    identities = await _identities(db, fingerprint, 6)
    identities[0].first_seen = dt.datetime.now(dt.UTC) - dt.timedelta(days=3)
    await db.commit()

    await fingerprints.flag_duplicates(db)

    flags = (
        await db.execute(
            sa.select(Respondent.is_flagged).where(Respondent.fingerprint_hash == fingerprint)
        )
    ).scalars()
    assert not any(flags)
