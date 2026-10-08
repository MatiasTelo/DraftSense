"""Honeypots — CA-103, CA-301, CA-302, CA-308 y CA-309 de `03-criterios-aceptacion.md`.

Cubren las tres partes de `22-calidad-de-datos.md` §3: cómo se evalúan, con qué cadencia se sirven
y cuándo se retiran solas. Y la carga del catálogo desde el YAML (§3.3, nota del 16/09).
"""

from __future__ import annotations

import random
import uuid
from decimal import Decimal
from itertools import combinations, pairwise
from typing import Any

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Champion, Dimension, Patch, Question, QuestionType, Respondent
from app.seeds.honeypots import HoneypotCatalogError, seed_honeypots, validate_honeypots
from app.services import honeypots, question_stats, sessions, trust
from app.services import responses as responses_service
from app.services.questions import Space
from tests.conftest import (
    FAR,
    add_response,
    as_respondent,
    make_champions,
    make_dimensions,
    pairwise_question,
    requires_db,
    restrict_pool,
)

EXPECTED = {"choice": "a"}


# ------------------------------------------------------------------------------ sin base de datos


def test_coincidir_con_la_esperada_es_pasar() -> None:
    assert honeypots.evaluate({"choice": "a"}, EXPECTED) is True
    assert honeypots.evaluate({"choice": "b"}, EXPECTED) is False


def test_unknown_no_es_un_intento() -> None:
    """CA-308 — `unknown` es neutro: ni pasa ni falla."""
    assert honeypots.evaluate({"choice": "unknown"}, EXPECTED) is None


def test_solo_seis_dimensiones_admiten_honeypots() -> None:
    """ADR-013 — `scaling` y `pick` no tienen un hecho del kit que las resuelva."""
    assert {
        "mobility",
        "cc",
        "poke",
        "waveclear",
        "engage",
        "peel",
    } == honeypots.ELIGIBLE_DIMENSIONS


def _champion(champion_id: int) -> Champion:
    return Champion(
        champion_id=champion_id,
        riot_key=f"K{champion_id}",
        riot_name=f"C{champion_id}",
        display_name=f"C{champion_id}",
        roles=["mid"],
        image_url="https://example.invalid/x.png",
        patch_first_seen=1,
        pool_tier=1,
    )


def test_la_honeypot_elegida_no_esta_vista_y_el_pool_la_admite() -> None:
    dimension = Dimension(dimension_id=1, code="cc", label_en="CC", description_en="", prompt_en="")
    space = Space.of([_champion(1), _champion(2), _champion(3)], [dimension])
    seen = Question(
        question_id=10,
        type=QuestionType.PAIRWISE_DIMENSION,
        champion_a=1,
        champion_b=2,
        dimension_id=1,
        patch_id=1,
        is_honeypot=True,
    )
    fresh = Question(
        question_id=11,
        type=QuestionType.PAIRWISE_DIMENSION,
        champion_a=1,
        champion_b=3,
        dimension_id=1,
        patch_id=1,
        is_honeypot=True,
    )
    outside = Question(
        question_id=12,
        type=QuestionType.PAIRWISE_DIMENSION,
        champion_a=1,
        champion_b=99,
        dimension_id=1,
        patch_id=1,
        is_honeypot=True,
    )
    rng = random.Random(0)
    picks = {honeypots.pick_unseen([seen, fresh, outside], space, {10}, rng) for _ in range(50)}
    assert picks == {fresh}
    assert honeypots.pick_unseen([seen], space, {10}, rng) is None


# --------------------------------------------------------------------------- servidas por HTTP


async def _pool(
    db: AsyncSession, patch: Patch, count: int = 10
) -> tuple[list[Champion], list[Dimension]]:
    champions = await make_champions(db, patch, count, prefix="Hp")
    dimensions = await make_dimensions(db, ["hpdima", "hpdimb", "hpdimc"])
    await restrict_pool(db, champions, dimensions)
    return champions, dimensions


async def _honeypots(
    db: AsyncSession, patch: Patch, champions: list[Champion], dimension: Dimension, count: int
) -> list[Question]:
    pairs = list(combinations(champions, 2))[:count]
    return [
        await pairwise_question(
            db, patch, a, b, dimension, is_honeypot=True, expected_answer=EXPECTED
        )
        for a, b in pairs
    ]


async def _serve_honeypot_now(
    client: AsyncClient, db: AsyncSession, respondent: Respondent, token: str, patch: Patch
) -> tuple[int, str]:
    champions, dimensions = await _pool(db, patch)
    catalog = await _honeypots(db, patch, champions, dimensions[0], 3)
    respondent.next_honeypot_at = respondent.answers_count
    respondent.next_retest_at = FAR
    await db.commit()
    response = await as_respondent(client, token).get("/questions/next?count=1")
    question_id: int = response.json()["questions"][0]["question_id"]
    assert question_id in {q.question_id for q in catalog}
    return question_id, response.text


async def _answer(client: AsyncClient, token: str, question_id: int, choice: str) -> None:
    response = await as_respondent(client, token).post(
        "/responses",
        json={"question_id": question_id, "answer": {"choice": choice}, "response_time_ms": 2500},
    )
    assert response.status_code == 201


@requires_db
async def test_ca103_la_honeypot_servida_es_indistinguible(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    """El cuerpo crudo no trae ninguna marca, y la honeypot tiene la forma de cualquier tipo 1."""
    row, token = respondent
    _, raw = await _serve_honeypot_now(client, db, row, token, patch)

    assert "is_honeypot" not in raw
    assert "expected_answer" not in raw
    assert "honeypot" not in raw.lower()


@requires_db
@pytest.mark.parametrize(
    ("choice", "attempts", "passed", "expected_trust"),
    [
        pytest.param("b", 1, 0, "0.400", id="CA-302 falla su primera honeypot"),
        pytest.param("a", 1, 1, "0.600", id="pasa su primera honeypot"),
        pytest.param("unknown", 0, 0, "0.500", id="CA-308 unknown es neutro"),
    ],
)
async def test_la_respuesta_a_una_honeypot_actualiza_el_trust_en_el_acto(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    choice: str,
    attempts: int,
    passed: int,
    expected_trust: str,
) -> None:
    row, token = respondent
    question_id, _ = await _serve_honeypot_now(client, db, row, token, patch)

    await _answer(client, token, question_id, choice)

    await db.refresh(row)
    assert (row.honeypot_attempts, row.honeypot_passed) == (attempts, passed)
    assert row.trust_score == Decimal(expected_trust)
    # También con `unknown` se abre la ventana siguiente: 10 a 15 posiciones después de la 0.
    assert row.next_honeypot_at is not None
    assert 10 <= row.next_honeypot_at <= 15


@requires_db
async def test_ca303_el_trust_no_sale_por_la_api(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    """Ni en la respuesta del POST de una honeypot, ni en `/me`."""
    row, token = respondent
    question_id, _ = await _serve_honeypot_now(client, db, row, token, patch)
    posted = await as_respondent(client, token).post(
        "/responses",
        json={"question_id": question_id, "answer": {"choice": "b"}, "response_time_ms": 2500},
    )
    me = await as_respondent(client, token).get("/me")

    for body in (posted.text, me.text):
        assert "trust" not in body
        assert "honeypot" not in body


def _answer_for(question: dict[str, Any]) -> dict[str, Any]:
    match question["type"]:
        case "peak_timing":
            return {"minute": 20}
        case "lane_matchup":
            return {"choice": "even"}
        case _:
            return {"choice": "a"}


@requires_db
async def test_ca301_sesenta_preguntas_traen_entre_cuatro_y_seis_honeypots(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Y ninguna ventana de 15 preguntas seguidas queda sin una (22 §3.6)."""
    monkeypatch.setattr(responses_service, "PER_MINUTE", 10_000)
    _, token = respondent
    champions, dimensions = await _pool(db, patch)
    catalog = {q.question_id for q in await _honeypots(db, patch, champions, dimensions[0], 8)}
    http = as_respondent(client, token)

    positions: list[int] = []
    answered = 0
    while answered < 60:
        batch = (await http.get("/questions/next?count=10")).json()["questions"]
        assert batch, f"lote vacío en la posición {answered}"
        for question in batch[: 60 - answered]:
            if question["question_id"] in catalog:
                positions.append(answered)
            response = await http.post(
                "/responses",
                json={
                    "question_id": question["question_id"],
                    "answer": _answer_for(question),
                    "response_time_ms": 2500,
                },
            )
            assert response.status_code == 201
            answered += 1

    assert 4 <= len(positions) <= 6, positions
    for start in range(0, 60 - 14):
        assert any(start <= p <= start + 14 for p in positions), (start, positions)


@requires_db
async def test_ca301_con_la_precarga_del_frontend(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CA-301 como lo vive el frontend: pide 5 con dos tarjetas en cola y manda sus ids.

    Es el escenario que en staging produjo honeypots a dos posiciones de distancia (ADR-020).
    """
    monkeypatch.setattr(responses_service, "PER_MINUTE", 10_000)
    _, token = respondent
    champions, dimensions = await _pool(db, patch)
    catalog = {q.question_id for q in await _honeypots(db, patch, champions, dimensions[0], 8)}
    http = as_respondent(client, token)

    queue: list[dict[str, Any]] = []
    positions: list[int] = []
    answered = 0

    async def refill() -> None:
        ids = ",".join(str(q["question_id"]) for q in queue)
        batch = (await http.get(f"/questions/next?count=5&queued={ids}")).json()["questions"]
        known = {q["question_id"] for q in queue}
        # Con `queued`, el servidor no manda nada de lo que ya está en la cola.
        assert not known & {q["question_id"] for q in batch}
        queue.extend(batch)

    await refill()
    while answered < 60:
        assert queue, f"cola vacía en la posición {answered}"
        question = queue.pop(0)
        if question["question_id"] in catalog:
            positions.append(answered)
        response = await http.post(
            "/responses",
            json={
                "question_id": question["question_id"],
                "answer": _answer_for(question),
                "response_time_ms": 2500,
            },
        )
        assert response.status_code == 201
        answered += 1
        if len(queue) <= 2:
            await refill()

    assert 4 <= len(positions) <= 6, positions
    assert all(b - a >= 10 for a, b in pairwise(positions)), positions
    for start in range(0, 60 - 14):
        assert any(start <= p <= start + 14 for p in positions), (start, positions)


async def _due_now(db: AsyncSession, row: Respondent, patch: Patch) -> set[int]:
    champions, dimensions = await _pool(db, patch)
    catalog = await _honeypots(db, patch, champions, dimensions[0], 4)
    row.answers_count = 10
    row.next_honeypot_at = 10
    row.next_retest_at = FAR
    await db.commit()
    return {q.question_id for q in catalog}


async def _batch(
    client: AsyncClient, token: str, count: int, queued: list[int] | None = None
) -> list[int]:
    ids = ",".join(str(question_id) for question_id in queued or [])
    response = await as_respondent(client, token).get(f"/questions/next?count={count}&queued={ids}")
    assert response.status_code == 200
    return [q["question_id"] for q in response.json()["questions"]]


@requires_db
async def test_la_precarga_no_trae_una_segunda_honeypot(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    """Con la honeypot todavía en la cola del cliente, el lote nuevo no trae ninguna."""
    row, token = respondent
    catalog = await _due_now(db, row, patch)

    first = await _batch(client, token, 3)
    second = await _batch(client, token, 5, queued=first)

    served = set(first) & catalog
    assert len(served) == 1
    assert not set(second) & catalog
    assert not set(second) & set(first)
    await db.refresh(row)
    assert row.pending_honeypot in served


@requires_db
async def test_una_honeypot_perdida_se_vuelve_a_servir(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    """Una recarga llega sin cola: la pendiente vuelve en su lugar, no se esquiva recargando."""
    row, token = respondent
    catalog = await _due_now(db, row, patch)

    first = await _batch(client, token, 3)
    again = await _batch(client, token, 3)

    [honeypot] = set(first) & catalog
    assert again[0] == honeypot
    assert set(again) & catalog == {honeypot}


@requires_db
async def test_contestar_la_honeypot_libera_la_pendiente(
    client: AsyncClient, db: AsyncSession, respondent: tuple[Respondent, str], patch: Patch
) -> None:
    row, token = respondent
    catalog = await _due_now(db, row, patch)
    first = await _batch(client, token, 1)
    assert first[0] in catalog

    await _answer(client, token, first[0], "a")

    await db.refresh(row)
    assert row.pending_honeypot is None
    assert row.next_honeypot_at is not None
    assert 20 <= row.next_honeypot_at <= 25
    after = await _batch(client, token, 5)
    assert not set(after) & catalog


# ------------------------------------------------------------------------- el retiro automático


async def _answered_by(
    db: AsyncSession, question: Question, passes: int, fails: int, flagged_fails: int = 0
) -> list[Respondent]:
    """Respondedores que contestaron la honeypot, con los contadores que habría dejado el POST."""
    params = trust.DEFAULT_PARAMS
    people: list[Respondent] = []
    plan = [("a", False)] * passes + [("b", False)] * fails + [("b", True)] * flagged_fails
    for choice, flagged in plan:
        person, _ = await sessions.create(db, f"huella-hp-{uuid.uuid4()}")
        await add_response(db, person, question, {"choice": choice})
        person.honeypot_attempts = 1
        person.honeypot_passed = int(choice == "a")
        person.is_flagged = flagged
        trust.refresh(person, params)
        people.append(person)
    await db.commit()
    return people


@requires_db
async def test_ca309_la_honeypot_mala_se_retira_y_el_trust_se_recalcula(
    db: AsyncSession, patch: Patch
) -> None:
    """0.80 de pass rate sobre 40 intentos: se retira y los afectados vuelven a 0.500."""
    champions, dimensions = await _pool(db, patch, count=4)
    [bad] = await _honeypots(db, patch, champions, dimensions[0], 1)
    people = await _answered_by(db, bad, passes=32, fails=8)
    failed = people[-1]
    assert failed.trust_score == Decimal("0.400")

    result = await question_stats.refresh(db)

    await db.refresh(bad)
    await db.refresh(failed)
    assert result.retired_honeypots == [bad.question_id]
    assert bad.is_honeypot is False
    assert (failed.honeypot_attempts, failed.honeypot_passed) == (0, 0)
    assert failed.trust_score == Decimal("0.500")


@requires_db
async def test_con_menos_de_40_intentos_no_se_evalua(db: AsyncSession, patch: Patch) -> None:
    """El piso de `quality.honeypot_min_attempts` (22 §3.4, nota del 16/09)."""
    champions, dimensions = await _pool(db, patch, count=4)
    [early] = await _honeypots(db, patch, champions, dimensions[0], 1)
    await _answered_by(db, early, passes=31, fails=8)

    result = await question_stats.refresh(db)

    await db.refresh(early)
    assert result.retired_honeypots == []
    assert early.is_honeypot is True


@requires_db
async def test_los_marcados_no_cuentan_para_el_pass_rate(db: AsyncSession, patch: Patch) -> None:
    """Si contaran, un grupo de identidades fabricadas podría retirar las honeypots."""
    champions, dimensions = await _pool(db, patch, count=4)
    [target] = await _honeypots(db, patch, champions, dimensions[0], 1)
    await _answered_by(db, target, passes=36, fails=0, flagged_fails=20)

    await question_stats.refresh(db)

    await db.refresh(target)
    assert target.is_honeypot is True


# ------------------------------------------------------------------------------ la carga del YAML


def _entry(a: str, b: str, dimension: str = "mobility", choice: str = "a") -> dict[str, Any]:
    return {
        "champion_a": a,
        "champion_b": b,
        "dimension": dimension,
        "expected": {"choice": choice},
        "rationale": f"{a} tiene un desplazamiento en su E; {b} no tiene ninguno.",
    }


def test_la_validacion_rechaza_lo_que_adr013_no_admite() -> None:
    entries = [
        _entry("X", "Y", dimension="scaling"),
        {**_entry("X", "Z"), "rationale": "  "},
        _entry("X", "W", choice="unknown"),
        _entry("P", "Q"),
        _entry("Q", "P"),
        _entry("R", "R"),
    ]
    problems = validate_honeypots(entries)
    joined = "\n".join(problems)
    assert "no admite honeypots" in joined
    assert "rationale es obligatorio" in joined
    assert "expected tiene que ser" in joined
    assert "par repetido" in joined
    assert "el mismo" in joined
    assert validate_honeypots([_entry("X", "Y")]) == []


async def _catalog_pool(db: AsyncSession, patch: Patch) -> tuple[list[Champion], Dimension]:
    champions = await make_champions(db, patch, 3, prefix="Cat")
    [mobility] = await make_dimensions(db, ["mobility"])
    return champions, mobility


async def _stored(db: AsyncSession, patch: Patch, dimension: Dimension) -> list[Question]:
    return list(
        (
            await db.execute(
                sa.select(Question)
                .where(
                    Question.patch_id == patch.patch_id,
                    Question.dimension_id == dimension.dimension_id,
                )
                .order_by(Question.question_id)
            )
        ).scalars()
    )


@requires_db
async def test_la_carga_pone_la_forma_canonica_e_invierte_la_esperada(
    db: AsyncSession, patch: Patch
) -> None:
    champions, mobility = await _catalog_pool(db, patch)
    low, high = champions[0], champions[1]

    result = await seed_honeypots(db, patch.patch_id, [_entry(high.display_name, low.display_name)])

    [stored] = await _stored(db, patch, mobility)
    assert result.created == 1
    assert (stored.champion_a, stored.champion_b) == (low.champion_id, high.champion_id)
    assert stored.is_honeypot is True
    assert stored.expected_answer == {"choice": "b"}


@requires_db
async def test_la_carga_es_idempotente(db: AsyncSession, patch: Patch) -> None:
    champions, mobility = await _catalog_pool(db, patch)
    entries = [_entry(champions[0].display_name, champions[1].display_name)]

    await seed_honeypots(db, patch.patch_id, entries)
    again = await seed_honeypots(db, patch.patch_id, entries)

    assert (again.created, again.unchanged) == (0, 1)
    assert len(await _stored(db, patch, mobility)) == 1


@requires_db
async def test_una_retirada_no_vuelve_sin_force(db: AsyncSession, patch: Patch) -> None:
    champions, mobility = await _catalog_pool(db, patch)
    entries = [_entry(champions[0].display_name, champions[1].display_name)]
    await seed_honeypots(db, patch.patch_id, entries)
    [stored] = await _stored(db, patch, mobility)
    stored.is_honeypot = False
    await db.commit()

    kept = await seed_honeypots(db, patch.patch_id, entries)
    await db.refresh(stored)
    assert stored.is_honeypot is False
    assert len(kept.skipped) == 1 and "--force" in kept.skipped[0]

    forced = await seed_honeypots(db, patch.patch_id, entries, force=True)
    await db.refresh(stored)
    assert forced.reactivated == 1
    assert stored.is_honeypot is True


@requires_db
async def test_no_convierte_una_pregunta_que_ya_se_contesto(db: AsyncSession, patch: Patch) -> None:
    champions, mobility = await _catalog_pool(db, patch)
    answered = await pairwise_question(db, patch, champions[0], champions[1], mobility)
    unanswered = await pairwise_question(db, patch, champions[0], champions[2], mobility)
    someone, _ = await sessions.create(db, f"huella-cat-{uuid.uuid4()}")
    await add_response(db, someone, answered, {"choice": "a"})

    result = await seed_honeypots(
        db,
        patch.patch_id,
        [
            _entry(champions[0].display_name, champions[1].display_name),
            _entry(champions[0].display_name, champions[2].display_name),
        ],
    )

    await db.refresh(answered)
    await db.refresh(unanswered)
    assert result.converted == 1
    assert len(result.skipped) == 1 and "respuestas" in result.skipped[0]
    assert answered.is_honeypot is False
    assert unanswered.is_honeypot is True


@requires_db
async def test_rechaza_campeones_fuera_del_nucleo(db: AsyncSession, patch: Patch) -> None:
    """Una honeypot con un campeón que nunca aparece en las preguntas comunes se delataría."""
    champions, mobility = await _catalog_pool(db, patch)
    champions[2].pool_tier = 3
    await db.commit()

    with pytest.raises(HoneypotCatalogError) as caught:
        await seed_honeypots(
            db,
            patch.patch_id,
            [
                _entry(champions[0].display_name, champions[2].display_name),
                _entry(champions[0].display_name, "No Existe"),
            ],
        )

    joined = " ".join(caught.value.problems)
    assert "no es de tier 1" in joined
    assert "no existe el campeón No Existe" in joined
    assert await _stored(db, patch, mobility) == []
