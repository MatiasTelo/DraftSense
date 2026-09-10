"""Tabla de posiciones — CA-313 y CA-303 de `docs/03-criterios-aceptacion.md` §8."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Respondent
from app.services import leaderboard, sessions
from tests.conftest import as_respondent, requires_db


async def _respondent(
    db: AsyncSession, *, answers: int, trust: str = "0.500", flagged: bool = False
) -> Respondent:
    row, _ = await sessions.create(db, f"fp-{answers}-{trust}-{flagged}")
    row.answers_count = answers
    row.trust_score = Decimal(trust)
    row.is_flagged = flagged
    await db.commit()
    return row


@requires_db
async def test_la_tabla_filtra_dos_veces(
    db: AsyncSession, respondent: tuple[Respondent, str]
) -> None:
    """CA-313 — quedan fuera el marcado y el de trust bajo, aunque lideren por volumen."""
    viewer, _ = respondent
    marcado = await _respondent(db, answers=9_000_000, flagged=True)
    desconfiado = await _respondent(db, answers=8_000_000, trust="0.200")
    honesto = await _respondent(db, answers=7_000_000, trust="0.500")

    table = await leaderboard.build(db, "all", viewer, dt.datetime.now(dt.UTC))

    aliases = [entry.alias for entry in table.entries]
    assert honesto.alias in aliases
    assert marcado.alias not in aliases
    assert desconfiado.alias not in aliases


@requires_db
async def test_el_umbral_es_la_misma_clave_que_el_export(
    db: AsyncSession, respondent: tuple[Respondent, str]
) -> None:
    """ADR-014 — el filtro usa literalmente `export.min_trust`, no una copia.

    Se mueve la clave y la tabla tiene que cambiar sola. Con dos parámetros independientes, uno
    se desincronizaría del otro en la primera calibración.
    """
    from app.models import AppSetting
    from app.services import app_settings

    viewer, _ = respondent
    justo_debajo = await _respondent(db, answers=6_000_000, trust="0.250")

    table = await leaderboard.build(db, "all", viewer, dt.datetime.now(dt.UTC))
    assert justo_debajo.alias not in [e.alias for e in table.entries]

    # Un UPSERT y no un INSERT: la clave la siembra `seed-settings`, así que el test tiene que
    # valer igual contra una base recién migrada y contra una ya sembrada.
    await db.execute(
        pg_insert(AppSetting)
        .values(key="export.min_trust", value=0.10, updated_by="test")
        .on_conflict_do_update(index_elements=[AppSetting.key], set_={"value": 0.10})
    )
    await db.commit()
    app_settings.reset_cache()
    leaderboard.reset_cache()

    table = await leaderboard.build(db, "all", viewer, dt.datetime.now(dt.UTC))
    assert justo_debajo.alias in [e.alias for e in table.entries]


@requires_db
async def test_marca_al_que_mira(
    db: AsyncSession, respondent: tuple[Respondent, str]
) -> None:
    """`is_you` señala al respondedor de la petición, y sólo a él."""
    viewer, _ = respondent
    viewer.answers_count = 5_000_000
    await db.commit()

    table = await leaderboard.build(db, "all", viewer, dt.datetime.now(dt.UTC))

    yours = [entry for entry in table.entries if entry.is_you]
    assert len(yours) == 1
    assert yours[0].alias == viewer.alias


@requires_db
async def test_el_trust_no_se_filtra(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str]
) -> None:
    """CA-303 — ninguna respuesta del endpoint permite despejar el trust de nadie."""
    _, token = respondent
    await _respondent(db, answers=4_000_000, trust="0.910")

    response = await as_respondent(client, token).get("/leaderboard?window=all")

    assert response.status_code == 200
    raw = response.text
    assert "trust" not in raw
    assert "0.910" not in raw
    for entry in response.json()["entries"]:
        assert set(entry) == {"rank", "alias", "answers_count", "is_you"}


@requires_db
async def test_ventana_invalida(
    client: AsyncClient, respondent: tuple[Respondent, str]
) -> None:
    """`docs/12-api.md` §2.6 — `window` sólo admite day, week y all."""
    _, token = respondent
    response = await as_respondent(client, token).get("/leaderboard?window=month")

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_parameter"
    assert error["field"] == "window"


@requires_db
async def test_las_tres_ventanas_responden(
    client: AsyncClient, respondent: tuple[Respondent, str]
) -> None:
    """Las ventanas de día y semana cuentan sobre `responses`; la total, sobre el contador."""
    _, token = respondent
    http = as_respondent(client, token)

    for window in leaderboard.WINDOWS:
        response = await http.get(f"/leaderboard?window={window}")
        assert response.status_code == 200, window
        assert response.json()["window"] == window
