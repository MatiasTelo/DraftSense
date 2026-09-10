"""Perfil y rachas — CA-303, CA-310, CA-311 y CA-312.

Las rachas se prueban contra el service y no contra HTTP: son lógica pura sobre columnas de la
propia fila, y hacerlas pasar por el endpoint obligaría a fabricar 20 preguntas para observar un
contador. Es la razón de ser de la capa de services (ADR-015).
"""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy import Engine, event
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Champion, Dimension, Patch, Question, QuestionType, Respondent, Response
from app.services import profile, streaks
from tests.conftest import as_respondent, requires_db

BUENOS_AIRES = dt.timezone(dt.timedelta(hours=-3))


def _at(year: int, month: int, day: int, hour: int = 12) -> dt.datetime:
    """Un instante en horario argentino, que es donde se define el día (§2.2)."""
    return dt.datetime(year, month, day, hour, tzinfo=BUENOS_AIRES)


# ------------------------------------------------------------------------------- rachas


@requires_db
async def test_la_racha_corta_con_la_pausa(
    db: AsyncSession, respondent: tuple[Respondent, str]
) -> None:
    """CA-310 — 31 minutos de pausa dejan `current_streak` en 1 y `best_streak` en 12."""
    row, _ = respondent
    row.current_streak = 12
    row.best_streak = 12
    row.last_seen = _at(2026, 9, 9, 10)

    await streaks.apply(db, row, _at(2026, 9, 9, 10) + dt.timedelta(minutes=31))

    assert row.current_streak == 1
    assert row.best_streak == 12


@requires_db
async def test_la_racha_sigue_dentro_de_la_ventana(
    db: AsyncSession, respondent: tuple[Respondent, str]
) -> None:
    """El otro lado de CA-310: 29 minutos no la cortan."""
    row, _ = respondent
    row.current_streak = 12
    row.best_streak = 12
    row.last_seen = _at(2026, 9, 9, 10)

    await streaks.apply(db, row, _at(2026, 9, 9, 10) + dt.timedelta(minutes=29))

    assert row.current_streak == 13
    assert row.best_streak == 13


@requires_db
async def test_la_racha_de_dias_suma_una_vez_por_dia(
    db: AsyncSession, respondent: tuple[Respondent, str]
) -> None:
    """CA-311 — 20 respuestas en un día suman exactamente 1, no 4 ni 16."""
    row, _ = respondent
    row.last_seen = _at(2026, 9, 9, 9)

    for minute in range(20):
        await streaks.apply(db, row, _at(2026, 9, 9, 10) + dt.timedelta(minutes=minute))

    assert row.answers_today == 20
    assert row.current_day_streak == 1
    assert row.best_day_streak == 1


@requires_db
async def test_la_racha_de_dias_encadena_y_se_corta(
    db: AsyncSession, respondent: tuple[Respondent, str]
) -> None:
    """CA-311 — días consecutivos encadenan; saltear un día calendario reinicia en 1."""
    row, _ = respondent
    row.last_seen = _at(2026, 9, 9, 9)

    for day in (9, 10):
        for minute in range(5):
            await streaks.apply(db, row, _at(2026, 9, day, 10) + dt.timedelta(minutes=minute))
    assert row.current_day_streak == 2
    assert row.best_day_streak == 2

    # Se saltea el 11 entero.
    for minute in range(5):
        await streaks.apply(db, row, _at(2026, 9, 12, 10) + dt.timedelta(minutes=minute))

    assert row.current_day_streak == 1
    assert row.best_day_streak == 2


@requires_db
async def test_la_racha_de_dias_no_suma_bajo_el_umbral(
    db: AsyncSession, respondent: tuple[Respondent, str]
) -> None:
    """Cuatro respuestas no alcanzan: el umbral de 5 existe para que la racha signifique algo."""
    row, _ = respondent
    row.last_seen = _at(2026, 9, 9, 9)

    for minute in range(4):
        await streaks.apply(db, row, _at(2026, 9, 9, 10) + dt.timedelta(minutes=minute))

    assert row.answers_today == 4
    assert row.current_day_streak == 0


# ------------------------------------------------------------------------------- GET /me


@requires_db
async def test_el_trust_score_no_se_expone(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str]
) -> None:
    """CA-303 — ni el valor ni ninguna métrica de la que se pueda despejar."""
    row, token = respondent
    row.trust_score = 0.812  # type: ignore[assignment]
    await db.commit()

    response = await as_respondent(client, token).get("/me")

    assert response.status_code == 200
    raw = response.text
    assert "trust" not in raw
    assert "0.812" not in raw
    assert "honeypot" not in raw
    assert set(response.json()) == {
        "answers_count",
        "current_streak",
        "best_streak",
        "current_day_streak",
        "best_day_streak",
        "agreement_rate",
        "coverage",
        "rank_percentile",
        "alias",
    }


@requires_db
async def test_el_alias_no_es_un_identificador(
    client: AsyncClient, respondent: tuple[Respondent, str]
) -> None:
    """CA-312 — no se deriva del `respondent_id` ni de la huella."""
    row, token = respondent
    response = await as_respondent(client, token).get("/me")

    alias = response.json()["alias"]
    assert alias is not None
    assert alias.count("-") == 2
    assert str(row.respondent_id) not in alias
    assert row.fingerprint_hash not in alias
    # Ningún tramo del alias sale del identificador: se sortea con `secrets`.
    assert not any(part in str(row.respondent_id) for part in alias.split("-"))


@requires_db
async def test_cobertura_por_tipo(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """Los cinco tipos aparecen siempre, los que no tienen respuestas en cero."""
    row, token = respondent
    low, high = sorted(c.champion_id for c in champions[:2])
    question = Question(
        type=QuestionType.PAIRWISE_DIMENSION,
        champion_a=low,
        champion_b=high,
        dimension_id=dimension.dimension_id,
        patch_id=patch.patch_id,
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)

    db.add(
        Response(
            respondent_id=row.respondent_id,
            question_id=question.question_id,
            type=QuestionType.PAIRWISE_DIMENSION,
            patch_id=patch.patch_id,
            answer={"choice": "a"},
            response_time_ms=1200,
        )
    )
    await db.commit()

    coverage = (await as_respondent(client, token).get("/me")).json()["coverage"]

    assert coverage["pairwise_dimension"] == 1
    assert coverage["peak_timing"] == 0
    assert set(coverage) == {t.value for t in QuestionType}


@requires_db
async def test_percentil_de_contribucion(
    db: AsyncSession, respondent: tuple[Respondent, str]
) -> None:
    """El que menos aportó queda en 0.0; el percentil sube con las respuestas."""
    row, _ = respondent
    row.answers_count = 0
    await db.commit()
    assert await profile.rank_percentile(db, row) == 0.0

    total = (
        await db.execute(
            sa.select(sa.func.count()).select_from(Respondent).where(~Respondent.is_flagged)
        )
    ).scalar_one()
    row.answers_count = 10_000_000
    await db.commit()
    assert await profile.rank_percentile(db, row) == (total - 1) / total


@requires_db
async def test_el_perfil_no_escala_con_el_historial(
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """El perfil se calcula en vivo: la cantidad de consultas no puede depender del historial.

    Se cuentan consultas y no milisegundos a propósito. El reloj de esta máquina mide sobre todo
    la latencia hasta la base de staging, que es ruido; lo que decide si `GET /me` entra en
    presupuesto en producción es que no haga una consulta por respuesta. Si alguien reemplaza el
    barrido por un bucle con un SELECT adentro, este test lo detecta y el cronómetro no.
    """
    row, _ = respondent
    low, high = sorted(c.champion_id for c in champions[:2])

    async def add_answered_question() -> None:
        """Una pregunta con consenso y la respuesta del respondedor a ella."""
        question = Question(
            type=QuestionType.PAIRWISE_DIMENSION,
            champion_a=low,
            champion_b=high,
            dimension_id=dimension.dimension_id,
            patch_id=patch.patch_id,
            answer_counts={"a": 30, "b": 10},
        )
        db.add(question)
        await db.commit()
        await db.refresh(question)
        db.add(
            Response(
                respondent_id=row.respondent_id,
                question_id=question.question_id,
                type=QuestionType.PAIRWISE_DIMENSION,
                patch_id=patch.patch_id,
                answer={"choice": "a"},
                response_time_ms=1000,
            )
        )
        await db.commit()

    async def count_queries() -> int:
        executed = 0

        # Las sentencias de control de transacción también pasan por este evento, y el
        # savepoint que abre la sesión después de un commit aparecería como una consulta de más
        # en unas corridas y no en otras.
        control = ("SAVEPOINT", "RELEASE", "ROLLBACK", "BEGIN", "COMMIT")

        def on_execute(
            _conn: object,
            _cursor: object,
            statement: str,
            *_args: object,
            **_kwargs: object,
        ) -> None:
            nonlocal executed
            if not statement.strip().upper().startswith(control):
                executed += 1

        # El listener va sobre la clase `Engine`: el bind de la sesión de test es una
        # conexión, no un engine, y no expone `sync_engine`.
        event.listen(Engine, "before_cursor_execute", on_execute)
        try:
            await profile.agreement_rate(db, row)
            await profile.coverage(db, row)
            await profile.rank_percentile(db, row)
        finally:
            event.remove(Engine, "before_cursor_execute", on_execute)
        return executed

    await add_answered_question()
    # Una pasada previa para calentar la caché de `app_settings`: si no, la primera medición
    # incluye la carga de los parámetros y la segunda no, y la diferencia se leería como si el
    # perfil escalara con el historial.
    await profile.agreement_rate(db, row)
    with_one = await count_queries()

    # El orden canónico impide repetir el mismo par, así que la segunda pregunta usa otro.
    low, high = sorted(c.champion_id for c in champions[2:4])
    await add_answered_question()
    with_two = await count_queries()

    assert with_one == with_two, "el perfil hace más consultas a medida que crece el historial"
    assert with_one <= 6, f"{with_one} consultas para armar el perfil es demasiado"
