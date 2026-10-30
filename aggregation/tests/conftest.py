"""Fixtures del pipeline. Las de base siguen el patrón de `backend/tests/conftest.py`: un engine
por test y una transacción externa que se revierte, con los `commit()` del código convertidos en
savepoints. Nada de lo que escribe un test queda en la base.

Los tests que necesitan base se saltean sin `DS_DATABASE_URL`. **Apuntalo al Postgres de Docker**
(127.0.0.1:5433), nunca a staging: el `.env` del backend apunta a staging.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import get_settings
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
    Trait,
)
from app.services import app_settings

requires_db = pytest.mark.skipif(
    not os.getenv("DS_DATABASE_URL"), reason="requiere DS_DATABASE_URL apuntando a un Postgres"
)


@pytest.fixture
async def connection() -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
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
    app_settings.reset_cache()
    async with maker() as session:
        yield session
    app_settings.reset_cache()


@dataclass(slots=True)
class World:
    """Un pool chico y aislado del resto de la base, dentro de la transacción del test."""

    session: AsyncSession
    patches: dict[str, Patch]
    champions: list[Champion]
    dimension: Dimension
    traits: list[Trait]
    respondents: list[Respondent] = field(default_factory=list)
    questions: dict[tuple[Any, ...], Question] = field(default_factory=dict)

    async def respondent(self, trust: str = "0.800", rank: str | None = None) -> Respondent:
        row = Respondent(
            session_token_hash=uuid.uuid4().hex,
            fingerprint_hash=f"agg-{uuid.uuid4()}",
            trust_score=Decimal(trust),
            declared_rank=rank,
        )
        self.session.add(row)
        await self.session.commit()
        self.respondents.append(row)
        return row

    async def question(self, **columns: Any) -> Question:
        key = (repr(sorted(columns.items(), key=lambda kv: kv[0])),)
        if key in self.questions:
            return self.questions[key]
        columns.setdefault("patch_id", self.patches["current"].patch_id)
        row = Question(**columns)
        self.session.add(row)
        await self.session.commit()
        self.questions[key] = row
        return row

    async def answer(
        self,
        respondent: Respondent,
        question: Question,
        answer: dict[str, Any],
        created: dt.datetime | None = None,
        is_retest_of: int | None = None,
    ) -> Response:
        row = Response(
            respondent_id=respondent.respondent_id,
            question_id=question.question_id,
            type=question.type,
            patch_id=question.patch_id,
            answer=answer,
            response_time_ms=3000,
            is_retest_of=is_retest_of,
            created_at=created or dt.datetime(2030, 3, 10, 12, tzinfo=dt.UTC),
        )
        self.session.add(row)
        await self.session.commit()
        return row


async def set_setting(session: AsyncSession, key: str, value: Any) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    statement = pg_insert(AppSetting).values(key=key, value=value)
    await session.execute(
        statement.on_conflict_do_update(index_elements=[AppSetting.key], set_={"value": value})
    )
    await session.commit()
    app_settings.reset_cache()


@pytest.fixture
async def world(db: AsyncSession) -> World:
    """Tres parches de 2030, el último vigente; seis campeones de tier 1 que son los únicos del
    pool habilitado; una dimensión y dos atributos activos, solos."""
    await db.execute(sa.update(Patch).values(is_current=False))
    patches = {}
    for name, version, released in (
        ("old", "90.18", dt.date(2030, 1, 1)),
        ("mid", "90.19", dt.date(2030, 2, 1)),
        ("current", "90.20", dt.date(2030, 3, 1)),
    ):
        row = Patch(version=version, released_at=released, is_current=name == "current")
        db.add(row)
        patches[name] = row
    await db.commit()

    await db.execute(sa.update(Champion).values(pool_tier=3))
    roles: Sequence[list[LaneRole]] = (
        [LaneRole.MID],
        [LaneRole.MID],
        [LaneRole.MID],
        [LaneRole.ADC],
        [LaneRole.SUPPORT],
        [LaneRole.ADC, LaneRole.SUPPORT],
    )
    champions = [
        Champion(
            riot_key=f"AggChamp{i}",
            riot_name=f"Agg Champ {i}",
            display_name=f"Agg Champ {i}",
            roles=list(r),
            image_url=f"https://example.invalid/agg{i}.png",
            patch_first_seen=patches["current"].patch_id,
            pool_tier=1,
        )
        for i, r in enumerate(roles)
    ]
    db.add_all(champions)

    await db.execute(sa.update(Dimension).values(is_active=False))
    dimension = Dimension(
        code="aggdim",
        label_en="Aggdim",
        description_en="What aggdim means.",
        prompt_en="Who has more aggdim?",
        display_order=1,
    )
    db.add(dimension)
    await db.execute(sa.update(Trait).values(is_active=False))
    traits = [
        Trait(code="aggalpha", label_en="Alpha", description_en="Alpha.", display_order=1),
        Trait(code="aggbeta", label_en="Beta", description_en="Beta.", display_order=2),
    ]
    db.add_all(traits)
    await db.commit()
    await set_setting(db, "sampler.enabled_pool_tiers", 1)
    await set_setting(db, "export.min_trust", 0.30)
    return World(db, patches, champions, dimension, traits)


def pairwise(world: World, a: int, b: int) -> dict[str, Any]:
    low, high = sorted((world.champions[a].champion_id, world.champions[b].champion_id))
    return {
        "type": QuestionType.PAIRWISE_DIMENSION,
        "champion_a": low,
        "champion_b": high,
        "dimension_id": world.dimension.dimension_id,
    }


def winner(world: World, question: Question, champion: int) -> dict[str, str]:
    """`{"choice": "a"}` si gana `champion`, en la forma canónica de la pregunta."""
    cid = world.champions[champion].champion_id
    return {"choice": "a" if question.champion_a == cid else "b"}
