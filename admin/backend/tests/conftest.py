"""Fixtures de los tests del panel.

A diferencia de `backend/tests/conftest.py`, **acá no se lee ningún `.env`**: la base de los tests
sale sólo de `DS_DATABASE_URL` en el entorno. `admin/.env` es el del servidor del laboratorio y
apunta a la base de producción; que `pytest` a secas corriera contra ella sería un accidente
esperando a pasar, aunque cada test se revierta.

Cada test corre dentro de una transacción que se revierte al terminar, con el mismo mecanismo del
backend: los `commit()` del código liberan un savepoint.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Final

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.models import (
    AppSetting,
    Champion,
    Dimension,
    LaneRole,
    Patch,
    Question,
    QuestionType,
    Respondent,
    Response,
)
from app.services import app_settings, sessions
from draftsense_admin.db import get_session
from draftsense_admin.main import create_app
from draftsense_admin.services.exporting import ExportRunner
from draftsense_admin.services.jobs import JobRunner

DATABASE_URL: Final = os.getenv("DS_DATABASE_URL", "")

requires_db = pytest.mark.skipif(
    not DATABASE_URL, reason="requiere DS_DATABASE_URL apuntando a un Postgres"
)


@pytest.fixture
async def connection() -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                yield conn
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
async def db(connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    async with maker() as session:
        yield session


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    app_settings.reset_cache()


@pytest.fixture
def admin_app(db: AsyncSession, tmp_path: Path) -> FastAPI:
    """El panel atado a la transacción del test.

    Los jobs también usan la sesión del test: si abrieran la suya, verían la base sin los datos
    sembrados por el test y escribirían fuera de la transacción que se revierte.
    """
    app = create_app(static_dir=tmp_path)

    async def override() -> AsyncIterator[AsyncSession]:
        yield db

    @asynccontextmanager
    async def shared() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_session] = override
    app.state.job_runner = JobRunner(shared)
    # Las exportaciones escriben en la carpeta temporal del test y corren en serie: un proceso
    # hijo no vería la transacción del test.
    app.state.export_runner = ExportRunner(shared, tmp_path / "exports", workers=1)
    return app


@pytest.fixture
async def client(admin_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://test/api") as http:
        yield http


# --------------------------------------------------------------------------------- datos de prueba


@pytest.fixture
async def patch(db: AsyncSession) -> Patch:
    """Un parche vigente. Se baja cualquier otro: `patches_single_current` admite uno solo."""
    import datetime as dt

    await db.execute(sa.update(Patch).values(is_current=False))
    row = Patch(version="99.99", released_at=dt.date(2026, 9, 1), is_current=True)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def make_champions(
    db: AsyncSession, patch: Patch, count: int, prefix: str = "Admin", tier: int = 1
) -> list[Champion]:
    rows = [
        Champion(
            riot_key=f"{prefix}Champ{i}",
            riot_name=f"{prefix} Champ {i}",
            display_name=f"{prefix} Champ {i}",
            roles=[LaneRole.MID],
            image_url=f"https://example.invalid/{prefix}{i}.png",
            patch_first_seen=patch.patch_id,
            pool_tier=tier,
        )
        for i in range(count)
    ]
    db.add_all(rows)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows


async def make_dimensions(db: AsyncSession, codes: Sequence[str]) -> list[Dimension]:
    found: list[Dimension] = []
    for index, code in enumerate(codes):
        row = (
            await db.execute(sa.select(Dimension).where(Dimension.code == code))
        ).scalar_one_or_none()
        if row is None:
            row = Dimension(
                code=code,
                label_en=code.title(),
                description_en=f"What {code} means.",
                prompt_en=f"Who has more {code}?",
                display_order=90 + index,
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
        found.append(row)
    return found


async def restrict_pool(
    db: AsyncSession, champions: Sequence[Champion], dimensions: Sequence[Dimension]
) -> None:
    """Deja habilitados sólo estos campeones y estas dimensiones, como en el backend."""
    await db.execute(sa.update(Champion).values(pool_tier=3))
    await db.execute(
        sa.update(Champion)
        .where(Champion.champion_id.in_([c.champion_id for c in champions]))
        .values(pool_tier=1)
    )
    await db.execute(sa.update(Dimension).values(is_active=False))
    await db.execute(
        sa.update(Dimension)
        .where(Dimension.dimension_id.in_([d.dimension_id for d in dimensions]))
        .values(is_active=True)
    )
    await db.commit()
    for champion in champions:
        await db.refresh(champion)


async def set_setting(db: AsyncSession, key: str, value: Any) -> None:
    statement = pg_insert(AppSetting).values(key=key, value=value)
    await db.execute(
        statement.on_conflict_do_update(index_elements=[AppSetting.key], set_={"value": value})
    )
    await db.commit()
    app_settings.reset_cache()


async def make_respondent(db: AsyncSession, fingerprint: str = "fp-admin") -> Respondent:
    respondent, _ = await sessions.create(db, fingerprint)
    return respondent


async def pairwise_question(
    db: AsyncSession,
    patch: Patch,
    first: Champion,
    second: Champion,
    dimension: Dimension,
    **columns: Any,
) -> Question:
    low, high = sorted((first.champion_id, second.champion_id))
    row = Question(
        type=QuestionType.PAIRWISE_DIMENSION,
        champion_a=low,
        champion_b=high,
        dimension_id=dimension.dimension_id,
        patch_id=patch.patch_id,
        **columns,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def add_response(
    db: AsyncSession, respondent: Respondent, question: Question, answer: dict[str, Any]
) -> Response:
    row = Response(
        respondent_id=respondent.respondent_id,
        question_id=question.question_id,
        type=question.type,
        patch_id=question.patch_id,
        answer=answer,
        response_time_ms=2000,
    )
    db.add(row)
    respondent.answers_count += 1
    await db.commit()
    await db.refresh(row)
    return row
