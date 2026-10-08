"""Configuración compartida de los tests.

Carga `backend/.env` al entorno antes de que los tests decidan si hay base de datos. Sin esto,
`pytest` a secas saltearía los tests que la requieren aunque el desarrollador ya tenga su `.env`
configurado, y sólo correrían en CI. Las variables que ya vienen del entorno tienen prioridad,
que es como CI inyecta su propio Postgres.

Las fixtures de base y de cliente HTTP viven acá desde la semana 2. **Cada test corre dentro de
una transacción que se revierte al terminar**: los tests de API escriben de verdad —hay INSERT,
restricciones y disparadores reales— pero no dejan nada. Es lo que permite correrlos contra la
base de staging sin contaminar el dataset que se le entrega al laboratorio.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

if _ENV_FILE.exists():
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

# El resto de los imports va después de poblar el entorno: `app.config` lo lee al construirse.
import datetime as dt  # noqa: E402
from collections.abc import AsyncIterator, Sequence  # noqa: E402
from typing import Any, Final  # noqa: E402

import pytest  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models import (  # noqa: E402
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
from app.services import app_settings, leaderboard, sessions  # noqa: E402

DATABASE_URL = os.getenv("DS_DATABASE_URL", "")

requires_db = pytest.mark.skipif(
    not DATABASE_URL, reason="requiere DS_DATABASE_URL apuntando a un Postgres"
)


@pytest.fixture
async def connection() -> AsyncIterator[AsyncConnection]:
    """Una conexión con una transacción externa que se revierte al final.

    El engine se crea y se descarta **por test**, en vez de usar el singleton de `app.db`. Es
    deliberado: `pytest-asyncio` abre un event loop nuevo para cada test, y una conexión de
    `asyncpg` queda atada al loop donde nació. Reusar el singleton hace que el segundo test que
    toque la base muera con "Event loop is closed", y el síntoma no señala la causa.
    """
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
    """Sesión atada a esa transacción.

    `join_transaction_mode="create_savepoint"` hace que los `commit()` del código de aplicación
    liberen un savepoint en vez de confirmar de verdad. Así el código bajo prueba commitea como
    en producción —y las restricciones diferidas se evalúan— pero el rollback externo lo deshace
    todo. Sin esto habría que borrar filas a mano y `responses` no admite DELETE.
    """
    maker = async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    async with maker() as session:
        yield session


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    """Las cachés en proceso sobreviven entre tests y los harían depender del orden."""
    app_settings.reset_cache()
    leaderboard.reset_cache()


@pytest.fixture
async def client(db: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Cliente HTTP contra la app, compartiendo la transacción del test."""

    async def override() -> AsyncIterator[AsyncSession]:
        yield db

    fastapi_app.dependency_overrides[get_session] = override
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="https://test/api/v1") as http:
        yield http
    fastapi_app.dependency_overrides.clear()


# --------------------------------------------------------------------------------- datos de prueba


@pytest.fixture
async def patch(db: AsyncSession) -> Patch:
    """Un parche vigente. Se baja cualquier otro: `patches_single_current` admite uno solo."""
    await db.execute(sa.update(Patch).values(is_current=False))
    row = Patch(version="99.99", released_at=dt.date(2026, 9, 1), is_current=True)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@pytest.fixture
async def dimension(db: AsyncSession) -> Dimension:
    row = Dimension(
        code="testdim",
        label_en="Engage",
        description_en="Starting fights on your terms.",
        prompt_en="Who has more engage?",
        display_order=99,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@pytest.fixture
async def champions(db: AsyncSession, patch: Patch) -> list[Champion]:
    """Cuatro campeones de tier 1, suficientes para armar pares distintos."""
    rows = [
        Champion(
            riot_key=f"TestChamp{i}",
            riot_name=f"Test Champ {i}",
            display_name=f"Test Champ {i}",
            roles=[LaneRole.MID],
            image_url=f"https://example.invalid/{i}.png",
            patch_first_seen=patch.patch_id,
            pool_tier=1,
        )
        for i in range(4)
    ]
    db.add_all(rows)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows


@pytest.fixture
async def respondent(db: AsyncSession) -> tuple[Respondent, str]:
    """Un respondedor con su token en claro, para poder mandar la cookie."""
    return await sessions.create(db, "fingerprint-de-prueba")


def as_respondent(client: AsyncClient, token: str) -> AsyncClient:
    """Deja al cliente autenticado como ese respondedor.

    La cookie se fija en el cliente y no por petición: httpx deprecó `cookies=` en la llamada
    porque su persistencia era ambigua.
    """
    client.cookies.set(sessions.COOKIE_NAME, token)
    return client


# ------------------------------------------------------------- ayudas del sampler y la calidad
#
# Los tests de la semana 5 tienen que pasar igual contra la base vacía de CI y contra staging, que
# tiene el pool real, las ocho dimensiones y —después de cargarlo— el catálogo de honeypots. Por eso
# arman su propio pool y reducen el habilitado a ése: todo lo que cambian lo revierte la
# transacción del test.

#: Lejos de cualquier lote: deja fuera de juego a las honeypots y los retests.
FAR: Final = 10_000


async def make_champions(
    db: AsyncSession,
    patch: Patch,
    count: int,
    roles: Sequence[LaneRole] = (LaneRole.TOP, LaneRole.MID),
    prefix: str = "Pool",
) -> list[Champion]:
    rows = [
        Champion(
            riot_key=f"{prefix}Champ{i}",
            riot_name=f"{prefix} Champ {i}",
            display_name=f"{prefix} Champ {i}",
            roles=list(roles),
            image_url=f"https://example.invalid/{prefix}{i}.png",
            patch_first_seen=patch.patch_id,
            pool_tier=1,
        )
        for i in range(count)
    ]
    db.add_all(rows)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows


async def make_dimensions(db: AsyncSession, codes: Sequence[str]) -> list[Dimension]:
    """Las dimensiones con esos códigos, creándolas si la base no las tiene (CI no las tiene)."""
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
    db: AsyncSession,
    champions: Sequence[Champion],
    dimensions: Sequence[Dimension] | None = None,
) -> None:
    """Deja habilitados sólo estos campeones y, si se pasan, sólo estas dimensiones."""
    await db.execute(sa.update(Champion).values(pool_tier=3))
    await db.execute(
        sa.update(Champion)
        .where(Champion.champion_id.in_([c.champion_id for c in champions]))
        .values(pool_tier=1)
    )
    if dimensions is not None:
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
    """Fija un parámetro de `app_settings` y vacía la caché, que si no lo escondería 60 s."""
    statement = pg_insert(AppSetting).values(key=key, value=value)
    await db.execute(
        statement.on_conflict_do_update(index_elements=[AppSetting.key], set_={"value": value})
    )
    await db.commit()
    app_settings.reset_cache()


async def pairwise_question(
    db: AsyncSession,
    patch: Patch,
    first: Champion,
    second: Champion,
    dimension: Dimension,
    **columns: Any,
) -> Question:
    """Una pregunta de tipo 1 en forma canónica, con las columnas extra que se pidan."""
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
    db: AsyncSession,
    respondent: Respondent,
    question: Question,
    answer: dict[str, Any],
    response_time_ms: int = 2000,
    is_retest_of: int | None = None,
) -> Response:
    """Una respuesta escrita directo, sin pasar por la API ni por la calidad.

    Suma a `answers_count` como lo haría el `POST`, para que las posiciones del respondedor
    (ADR-020) coincidan con sus filas.
    """
    row = Response(
        respondent_id=respondent.respondent_id,
        question_id=question.question_id,
        type=question.type,
        patch_id=question.patch_id,
        answer=answer,
        response_time_ms=response_time_ms,
        is_retest_of=is_retest_of,
    )
    db.add(row)
    respondent.answers_count += 1
    await db.commit()
    await db.refresh(row)
    return row
