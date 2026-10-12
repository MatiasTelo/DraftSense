"""Versionado por parche: registrar, activar y lo que pasa al cambiar (ADR-024).

El crudo versionado por parche (ADR-004) ya lo cubre
`test_responses.test_el_crudo_conserva_su_parche`. Acá se prueba la transición: que sólo
`activate` cambie el vigente, que lo rechace si al parche le falta el snapshot o las honeypots,
que quede auditado, y qué hace el sistema con lo que estaba en vuelo (`21-sampler.md` §8 y
`12-api.md` §2, notas del 11/10).
"""

from __future__ import annotations

import datetime as dt
import random

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AdminAudit,
    Champion,
    Dimension,
    Patch,
    PickRateSnapshot,
    Question,
    QuestionType,
    Respondent,
    Response,
)
from app.services import patches, sampler
from tests.conftest import (
    FAR,
    add_response,
    as_respondent,
    make_champions,
    make_dimensions,
    pad_pool,
    pairwise_question,
    requires_db,
    restrict_pool,
)

NEW = "99.98"


async def _current(db: AsyncSession) -> Patch | None:
    return (await db.execute(sa.select(Patch).where(Patch.is_current))).scalar_one_or_none()


async def _audits(db: AsyncSession) -> list[AdminAudit]:
    statement = sa.select(AdminAudit).order_by(AdminAudit.audit_id)
    return list((await db.execute(statement)).scalars())


async def _pool(db: AsyncSession, patch: Patch) -> tuple[list[Champion], list[Dimension]]:
    """Diez campeones y una dimensión habilitados: alcanza para servir rankings (ADR-022)."""
    champions = await pad_pool(db, await make_champions(db, patch, 5, prefix="Pt"))
    dimensions = await make_dimensions(db, ["ptdim"])
    await restrict_pool(db, champions, dimensions)
    return champions, dimensions


async def _make_ready(
    db: AsyncSession, patch: Patch, champions: list[Champion], dimension: Dimension
) -> Question:
    """Lo que `activate` exige: un snapshot de pick rate y una honeypot activa."""
    db.add(
        PickRateSnapshot(
            source="lolalytics",
            source_url="https://example.invalid/snapshot",
            captured_at=dt.date(2026, 10, 1),
            patch_id=patch.patch_id,
        )
    )
    await db.commit()
    return await pairwise_question(
        db,
        patch,
        champions[0],
        champions[1],
        dimension,
        is_honeypot=True,
        expected_answer={"choice": "a"},
    )


# ------------------------------------------------------------------------------ registrar y activar


@requires_db
async def test_registrar_no_cambia_el_vigente(db: AsyncSession, patch: Patch) -> None:
    """Los seeds registran: ni un parche nuevo ni actualizar uno existente lo activan."""
    created = await patches.register(db, NEW, dt.date(2026, 10, 7))
    again = await patches.register(db, NEW, dt.date(2026, 10, 8))

    assert again.patch_id == created.patch_id
    assert again.released_at == dt.date(2026, 10, 8)
    assert not again.is_current
    current = await _current(db)
    assert current is not None and current.patch_id == patch.patch_id


@requires_db
async def test_activar_un_parche_inexistente_falla(db: AsyncSession, patch: Patch) -> None:
    with pytest.raises(patches.PatchNotFoundError):
        await patches.activate(db, "98.97")

    current = await _current(db)
    assert current is not None and current.patch_id == patch.patch_id


@requires_db
async def test_sin_snapshot_ni_honeypots_se_rechaza(db: AsyncSession, patch: Patch) -> None:
    """Cada faltante se informa por separado, y el vigente no cambia ni se audita nada."""
    await patches.register(db, NEW)
    before = len(await _audits(db))

    with pytest.raises(patches.PatchActivationError) as error:
        await patches.activate(db, NEW)

    assert len(error.value.problems) == 2
    assert any("pick rate" in problem for problem in error.value.problems)
    assert any("honeypots" in problem for problem in error.value.problems)
    current = await _current(db)
    assert current is not None and current.patch_id == patch.patch_id
    assert len(await _audits(db)) == before


@requires_db
async def test_con_force_se_activa_igual_y_queda_auditado(
    db: AsyncSession, patch: Patch
) -> None:
    new = await patches.register(db, NEW)

    result = await patches.activate(db, NEW, force=True)

    assert result == patches.ActivationResult(new.patch_id, NEW, patch.version, changed=True)
    current = await _current(db)
    assert current is not None and current.patch_id == new.patch_id
    await db.refresh(patch)
    assert not patch.is_current
    last = (await _audits(db))[-1]
    assert last.action == "activate_patch"
    assert last.payload == {"patch_id": new.patch_id, "version": NEW, "previous": patch.version}


@requires_db
async def test_con_snapshot_y_honeypots_se_activa_sin_forzar(
    db: AsyncSession, patch: Patch
) -> None:
    champions, dimensions = await _pool(db, patch)
    new = await patches.register(db, NEW)
    await _make_ready(db, new, champions, dimensions[0])

    result = await patches.activate(db, NEW)

    assert result.changed
    current = await _current(db)
    assert current is not None and current.patch_id == new.patch_id


@requires_db
async def test_activar_el_vigente_no_hace_nada(db: AsyncSession, patch: Patch) -> None:
    """Repetir el comando no llena `admin_audit`, y no exige precondiciones que no cambian nada."""
    before = len(await _audits(db))

    result = await patches.activate(db, patch.version)

    assert not result.changed
    assert result.previous == patch.version
    assert len(await _audits(db)) == before


@requires_db
async def test_health_devuelve_el_parche_activado(
    client: AsyncClient, db: AsyncSession, patch: Patch
) -> None:
    await patches.register(db, NEW)
    await patches.activate(db, NEW, force=True)

    response = await client.get("/health")

    assert response.json()["current_patch"] == NEW


# ------------------------------------------------------------------------------ la transición


@requires_db
async def test_despues_de_activar_solo_se_sirve_el_parche_nuevo(
    db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    """Lo viejo conserva su parche y el sampler materializa todo contra el nuevo (ADR-004)."""
    row, _ = respondent
    champions, dimensions = await _pool(db, patch)
    old_question = await pairwise_question(db, patch, champions[0], champions[1], dimensions[0])
    old_response = await add_response(db, row, old_question, {"choice": "a"})
    row.next_honeypot_at = FAR
    row.next_retest_at = FAR
    await db.commit()
    new = await patches.register(db, NEW)
    await patches.activate(db, NEW, force=True)

    batch = await sampler.next_batch(db, row, 5, random.Random(3))

    assert batch
    served = [await db.get(Question, item.question_id) for item in batch]
    assert all(q is not None and q.patch_id == new.patch_id for q in served)
    await db.refresh(old_question)
    await db.refresh(old_response)
    assert old_question.patch_id == patch.patch_id
    assert old_response.patch_id == patch.patch_id


@requires_db
async def test_lo_pendiente_del_parche_viejo_se_descarta(
    db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    """La honeypot y el retest pendientes de otro parche no se vuelven a servir."""
    row, _ = respondent
    champions, dimensions = await _pool(db, patch)
    old_honeypot = await pairwise_question(
        db,
        patch,
        champions[2],
        champions[3],
        dimensions[0],
        is_honeypot=True,
        expected_answer={"choice": "a"},
    )
    old_question = await pairwise_question(db, patch, champions[0], champions[1], dimensions[0])
    old_response = await add_response(db, row, old_question, {"choice": "a"})
    new = await patches.register(db, NEW)
    new_honeypot = await _make_ready(db, new, champions, dimensions[0])
    await patches.activate(db, NEW)
    # Las dos cadencias vencidas en el primer lote, y las dos con un pendiente del parche viejo.
    row.pending_honeypot = old_honeypot.question_id
    row.pending_retest_of = old_response.response_id
    row.next_honeypot_at = row.answers_count
    row.next_retest_at = row.answers_count
    await db.commit()

    batch = await sampler.next_batch(db, row, 5, random.Random(5))

    ids = {item.question_id for item in batch}
    assert old_honeypot.question_id not in ids
    assert old_question.question_id not in ids
    assert new_honeypot.question_id in ids
    await db.refresh(row)
    assert row.pending_honeypot == new_honeypot.question_id
    # El parche nuevo no tiene respuestas que repetir: no queda ningún retest pendiente.
    assert row.pending_retest_of is None


@requires_db
async def test_una_respuesta_en_vuelo_se_acepta_con_su_parche(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
) -> None:
    """La pregunta se sirvió antes del cambio y se contesta después: entra con el parche viejo."""
    _, token = respondent
    champions, _ = await _pool(db, patch)
    question = Question(
        type=QuestionType.PEAK_TIMING, champion_a=champions[0].champion_id, patch_id=patch.patch_id
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)
    await patches.register(db, NEW)
    await patches.activate(db, NEW, force=True)

    response = await as_respondent(client, token).post(
        "/responses",
        json={
            "question_id": question.question_id,
            "answer": {"minute": 25},
            "response_time_ms": 4000,
        },
    )

    assert response.status_code == 201
    stored = (
        await db.execute(sa.select(Response).where(Response.question_id == question.question_id))
    ).scalar_one()
    assert stored.patch_id == patch.patch_id
