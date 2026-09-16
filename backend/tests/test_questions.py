"""Entrega de preguntas — CA-101 a CA-104 de `docs/03-criterios-aceptacion.md` §2.

Cubren los tres tipos que existen desde la semana 4: el 1, el 2 y la variante 1v1 del 3. El
sampler completo es de la semana 5.

**El sorteo se prueba sin azar.** Las funciones puras reciben un `random.Random` con semilla, y
los tests HTTP o bien afirman invariantes que valen para cualquier sorteo, o bien fuerzan el tipo
reemplazando `TYPE_WEIGHTS` y saltean el arranque subiendo `answers_count`. Tienen que pasar
igual contra la base de CI, que sólo tiene los campeones de los fixtures, y contra la de staging,
que tiene el pool real.
"""

from __future__ import annotations

import random
from typing import Any

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Champion, Dimension, LaneRole, Patch, Question, QuestionType, Respondent
from app.services import answers, question_texts
from app.services import questions as questions_service
from app.services.questions import (
    TYPE_WEIGHTS,
    Combination,
    Space,
    choose_type,
    draw_combination,
    lane_pools,
    materialize,
    render_lane,
    render_peak,
    role_label,
)
from tests.conftest import as_respondent, requires_db

PAIRWISE = QuestionType.PAIRWISE_DIMENSION
PEAK = QuestionType.PEAK_TIMING
LANE = QuestionType.LANE_MATCHUP
SERVED = frozenset({PAIRWISE, PEAK, LANE})


def _champion(champion_id: int, name: str, roles: list[LaneRole]) -> Champion:
    """Un campeón en memoria, sin base: alcanza para las funciones puras."""
    return Champion(
        champion_id=champion_id,
        riot_key=name.replace(" ", ""),
        riot_name=name,
        display_name=name,
        roles=roles,
        image_url=f"https://example.invalid/{champion_id}.png",
        patch_first_seen=1,
        pool_tier=1,
    )


def _question(question_id: int, question_type: QuestionType, **columns: Any) -> Question:
    """Una pregunta en memoria, para probar el render sin base."""
    return Question(question_id=question_id, type=question_type, patch_id=1, **columns)


def _force(monkeypatch: pytest.MonkeyPatch, question_type: QuestionType) -> None:
    """Deja un solo tipo con peso, para que el sorteo del tipo sea determinista."""
    monkeypatch.setattr(questions_service, "TYPE_WEIGHTS", {question_type: 1})


async def _skip_warmup(db: AsyncSession, respondent: Respondent, answers_count: int = 3) -> None:
    """Las tres primeras son siempre de tipo 1: sin esto no se puede observar otro tipo."""
    respondent.answers_count = answers_count
    await db.commit()


async def _only_in_pool(db: AsyncSession, champions: list[Champion]) -> None:
    """Deja el pool habilitado reducido a estos campeones, aunque la base tenga el real."""
    await db.execute(sa.update(Champion).values(pool_tier=3))
    await db.execute(
        sa.update(Champion)
        .where(Champion.champion_id.in_([c.champion_id for c in champions]))
        .values(pool_tier=1)
    )
    await db.commit()


# ----------------------------------------------------------- el tipo de cada posición, sin base


def test_las_tres_primeras_son_de_tipo_1() -> None:
    """CA-102 — con el tipo 1 disponible, las posiciones 0 a 2 nunca sortean."""
    for seed in range(100):
        rng = random.Random(seed)
        assert [choose_type(position, SERVED, rng) for position in range(3)] == [PAIRWISE] * 3


def test_sin_tipo_1_el_arranque_cae_a_la_mezcla() -> None:
    """Si el tipo 1 no tiene candidatas, el arranque no deja la sesión vacía."""
    assert choose_type(0, {PEAK}, random.Random(1)) is PEAK


def test_la_mezcla_respeta_los_pesos_renormalizados() -> None:
    """`docs/20-tipos-de-pregunta.md` §7, restringida a los tres tipos que existen."""
    rng = random.Random(1234)
    draws = [choose_type(3, SERVED, rng) for _ in range(20_000)]
    total = sum(TYPE_WEIGHTS.values())
    for question_type, weight in TYPE_WEIGHTS.items():
        assert draws.count(question_type) / len(draws) == pytest.approx(weight / total, abs=0.02)


def test_un_tipo_sin_candidatas_no_se_sortea() -> None:
    rng = random.Random(7)
    assert PAIRWISE not in {choose_type(5, {PEAK, LANE}, rng) for _ in range(1_000)}
    assert choose_type(0, set(), rng) is None


def test_los_pesos_son_los_de_la_composicion_documentada() -> None:
    """50 / 20 / 15 de §7. Si cambian acá, tiene que cambiar el documento primero."""
    assert TYPE_WEIGHTS == {PAIRWISE: 50, PEAK: 20, LANE: 15}


# ------------------------------------------------------------------------ el 1v1, sin base


def test_solo_top_mid_y_adc_generan_matchups() -> None:
    """§4.1 — la jungla no entra, y el support sólo juega el 2v2 de la semana 8."""
    champions = [
        _champion(1, "Lee Sin", [LaneRole.JUNGLE]),
        _champion(2, "Vi", [LaneRole.JUNGLE]),
        _champion(3, "Thresh", [LaneRole.SUPPORT]),
        _champion(4, "Nautilus", [LaneRole.SUPPORT]),
        _champion(5, "Darius", [LaneRole.TOP]),
        _champion(6, "Garen", [LaneRole.TOP]),
    ]
    assert set(lane_pools(champions)) == {LaneRole.TOP}


def test_un_rol_con_menos_de_dos_campeones_no_genera_matchups() -> None:
    """`docs/21-sampler.md` §8 — el rol se saltea, no es un error."""
    champions = [
        _champion(1, "Syndra", [LaneRole.MID]),
        _champion(2, "Zed", [LaneRole.MID]),
        _champion(3, "Darius", [LaneRole.TOP]),
    ]
    assert set(lane_pools(champions)) == {LaneRole.MID}
    assert Space.of(champions, []).available_types() == {PEAK, LANE}


def test_la_combinacion_del_1v1_es_canonica_y_comparte_rol() -> None:
    champions = [
        _champion(9, "Yasuo", [LaneRole.TOP, LaneRole.MID, LaneRole.ADC]),
        _champion(4, "Syndra", [LaneRole.MID]),
        _champion(7, "Zed", [LaneRole.MID]),
        _champion(2, "Darius", [LaneRole.TOP]),
        _champion(5, "Jinx", [LaneRole.ADC]),
    ]
    space = Space.of(champions, [])
    roles = {c.champion_id: set(c.roles) for c in champions}
    rng = random.Random(3)
    for _ in range(200):
        combination = draw_combination(LANE, space, rng)
        assert combination.champion_b is not None
        assert combination.role is not None
        assert combination.champion_a < combination.champion_b
        assert combination.role in roles[combination.champion_a]
        assert combination.role in roles[combination.champion_b]
        assert combination.dimension_id is None


# ---------------------------------------------------------------------- el render, sin base


def test_ca104_las_opciones_del_matchup_llevan_los_nombres() -> None:
    """CA-104 — «Syndra wins hard», no «A wins hard» ni una plantilla sin resolver."""
    syndra = _champion(134, "Syndra", [LaneRole.MID])
    zed = _champion(238, "Zed", [LaneRole.MID])
    question = _question(77310, LANE, champion_a=134, champion_b=238, role=LaneRole.MID)

    rendered = render_lane(question, {134: syndra, 238: zed})

    assert [(o.key, o.label) for o in rendered.options] == [
        ("a_strong", "Syndra wins hard"),
        ("a_slight", "Syndra wins slightly"),
        ("even", "Even"),
        ("b_slight", "Zed wins slightly"),
        ("b_strong", "Zed wins hard"),
    ]
    assert rendered.prompt == "Who wins this lane at 10 minutes?"
    assert [s.champions[0].name for s in rendered.sides] == ["Syndra", "Zed"]
    assert "label" not in rendered.model_dump()["sides"][0]


def test_la_etiqueta_del_rol_va_en_mayusculas() -> None:
    assert [role_label(r) for r in (LaneRole.TOP, LaneRole.MID, LaneRole.ADC)] == [
        "TOP",
        "MID",
        "ADC",
    ]
    jinx = _champion(1, "Jinx", [LaneRole.ADC])
    caitlyn = _champion(2, "Caitlyn", [LaneRole.ADC])
    question = _question(1, LANE, champion_a=1, champion_b=2, role=LaneRole.ADC)

    rendered = render_lane(question, {1: jinx, 2: caitlyn}).model_dump(mode="json")

    assert rendered["context"] == {"role": "adc", "label": "ADC"}


def test_el_pico_llega_compuesto_con_el_slider_del_contrato() -> None:
    """`docs/12-api.md` §2.3, campo por campo."""
    kayle = _champion(10, "Kayle", [LaneRole.TOP])
    question = _question(91002, PEAK, champion_a=10)

    rendered = render_peak(question, {10: kayle}).model_dump(mode="json")

    assert rendered == {
        "question_id": 91002,
        "type": "peak_timing",
        "prompt": "When does Kayle peak?",
        "help": {
            "label": "Power spike",
            "text": "The point in the game where this champion is at their strongest "
            "compared to everyone else.",
        },
        "subject": {
            "champions": [
                {
                    "id": 10,
                    "key": "Kayle",
                    "name": "Kayle",
                    "image_url": "https://example.invalid/10.png",
                }
            ]
        },
        "slider": {
            "min": 0,
            "max": 40,
            "step": 1,
            "default": 20,
            "unit": "min",
            "marks": [
                {"at": 0, "label": "laning"},
                {"at": 15, "label": "mid game"},
                {"at": 30, "label": "late game"},
            ],
        },
    }


def test_el_slider_y_las_opciones_coinciden_con_la_validacion() -> None:
    """Lo que se ofrece y lo que se acepta no pueden divergir: el cliente recibiría un 400."""
    assert question_texts.PEAK_MIN == answers.PEAK_MIN_MINUTE
    assert question_texts.PEAK_MAX == answers.PEAK_MAX_MINUTE
    assert question_texts.PEAK_MIN <= question_texts.PEAK_DEFAULT <= question_texts.PEAK_MAX
    assert tuple(question_texts.LANE_OPTION_TEMPLATES) == answers.LANE_MATCHUP_CHOICES


# ----------------------------------------------------------------------- el lote, por HTTP


@requires_db
async def test_entrega_por_lotes(
    client: AsyncClient,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """CA-101 — se piden 5, llegan 5, y ninguna repetida dentro del lote."""
    _, token = respondent
    response = await as_respondent(client, token).get("/questions/next?count=5")

    assert response.status_code == 200
    questions = response.json()["questions"]
    assert len(questions) == 5

    ids = [q["question_id"] for q in questions]
    assert len(set(ids)) == len(ids)


@requires_db
async def test_los_honeypots_son_indistinguibles(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """CA-103 — `is_honeypot` y `expected_answer` no aparecen en ninguna forma.

    Se inspecciona el cuerpo crudo y no el objeto parseado: un campo de más se colaría igual si
    sólo se miraran las claves que el schema declara. El lote se pide pasado el arranque para que
    incluya las tres formas de pregunta.
    """
    row, token = respondent
    await _skip_warmup(db, row)
    response = await as_respondent(client, token).get("/questions/next?count=10")

    raw = response.text
    assert "is_honeypot" not in raw
    assert "expected_answer" not in raw
    assert "exposure_count" not in raw
    assert "entropy" not in raw
    assert "answer_counts" not in raw


@requires_db
async def test_el_enunciado_llega_compuesto(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """CA-104 — el texto sale de `dimensions`, no de una plantilla sin resolver.

    Se compara contra la dimensión **de la pregunta que llegó**, no contra la del fixture: el
    sampler sortea entre todas las dimensiones activas, y con el catálogo sembrado el fixture es
    una de nueve. Amarrar el test a una en particular lo haría fallar según qué sorteo salga.
    """
    _, token = respondent
    response = await as_respondent(client, token).get("/questions/next?count=1")

    payload = response.json()["questions"][0]
    assert payload["type"] == "pairwise_dimension"

    source = (
        await db.execute(
            sa.select(Dimension)
            .join(Question, Question.dimension_id == Dimension.dimension_id)
            .where(Question.question_id == payload["question_id"])
        )
    ).scalar_one()

    assert payload["prompt"] == source.prompt_en
    assert payload["help"] == {"label": source.label_en, "text": source.description_en}
    assert "{" not in payload["prompt"]


@requires_db
async def test_toda_opcion_comparable_lleva_arreglo(
    client: AsyncClient,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """`docs/12-api.md` §1.2 — el cliente renderiza duplas y campeones con el mismo componente."""
    _, token = respondent
    response = await as_respondent(client, token).get("/questions/next?count=1")

    options = response.json()["questions"][0]["options"]
    assert [o["key"] for o in options] == ["a", "b", "unknown"]
    assert all(isinstance(o["champions"], list) for o in options)
    assert len(options[0]["champions"]) == 1
    assert options[2]["champions"] == []
    assert options[2]["label"] == "Not sure"
    # Un lado con campeón no lleva etiqueta: la clave no viaja, ni siquiera en `null` (§2.3).
    assert "label" not in options[0]

    champion = options[0]["champions"][0]
    assert set(champion) == {"id", "key", "name", "image_url"}


@requires_db
async def test_count_fuera_de_rango(
    client: AsyncClient, respondent: tuple[Respondent, str]
) -> None:
    """`docs/12-api.md` §3 — `invalid_parameter`, con el campo señalado."""
    _, token = respondent
    response = await as_respondent(client, token).get("/questions/next?count=99")

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_parameter"
    assert error["field"] == "count"


@requires_db
async def test_sin_pool_habilitado_devuelve_lote_vacio(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """Sin campeones de tier habilitado no hay de dónde sacar preguntas, y eso no es un error.

    El tier se baja explícitamente en vez de confiar en que la base esté vacía: el snapshot de
    pick rate deja 58 campeones en tier 1, y el test tiene que valer igual después de sembrarlo.
    """
    await db.execute(sa.update(Champion).values(pool_tier=3))
    await db.commit()

    _, token = respondent
    response = await as_respondent(client, token).get("/questions/next?count=5")

    assert response.status_code == 200
    assert response.json()["questions"] == []


# ------------------------------------------------------------------ la mezcla, por HTTP y con base


@requires_db
async def test_ca102_las_primeras_tres_son_de_tipo_1(
    client: AsyncClient,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """CA-102 — un respondedor sin respuestas empieza por el tipo más fácil de entender."""
    _, token = respondent
    response = await as_respondent(client, token).get("/questions/next?count=5")

    types = [q["type"] for q in response.json()["questions"]]
    assert types[:3] == ["pairwise_dimension"] * 3
    assert set(types) <= {t.value for t in SERVED}


@requires_db
async def test_el_arranque_cuenta_las_respuestas_previas(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La posición es la del respondedor, no la del lote: con 2 respuestas, sólo falta una."""
    row, token = respondent
    await _skip_warmup(db, row, answers_count=2)
    _force(monkeypatch, PEAK)

    response = await as_respondent(client, token).get("/questions/next?count=3")

    types = [q["type"] for q in response.json()["questions"]]
    assert types == ["pairwise_dimension", "peak_timing", "peak_timing"]


@requires_db
async def test_el_pico_llega_con_la_forma_del_contrato(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`docs/12-api.md` §2.3 — y el nombre del campeón ya sustituido en el enunciado."""
    row, token = respondent
    await _skip_warmup(db, row)
    await _only_in_pool(db, champions)
    _force(monkeypatch, PEAK)

    response = await as_respondent(client, token).get("/questions/next?count=1")

    payload = response.json()["questions"][0]
    assert set(payload) == {"question_id", "type", "prompt", "help", "subject", "slider"}
    subject = payload["subject"]["champions"]
    assert len(subject) == 1
    assert subject[0]["id"] in {c.champion_id for c in champions}
    assert payload["prompt"] == f"When does {subject[0]['name']} peak?"
    assert payload["help"]["label"] == "Power spike"
    assert payload["slider"]["default"] == 20

    stored = (
        await db.execute(sa.select(Question).where(Question.question_id == payload["question_id"]))
    ).scalar_one()
    assert stored.type is PEAK
    assert (stored.champion_b, stored.dimension_id, stored.role) == (None, None, None)


@requires_db
async def test_ca104_el_matchup_llega_con_los_nombres(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CA-104, por HTTP — el caso literal del criterio, Syndra contra Zed en mid."""
    pair = [
        Champion(
            riot_key=f"Test{name}",
            riot_name=name,
            display_name=name,
            roles=[LaneRole.MID],
            image_url=f"https://example.invalid/{name}.png",
            patch_first_seen=patch.patch_id,
            pool_tier=1,
        )
        for name in ("Syndra", "Zed")
    ]
    db.add_all(pair)
    await db.commit()
    row, token = respondent
    await _skip_warmup(db, row)
    await _only_in_pool(db, pair)
    _force(monkeypatch, LANE)

    response = await as_respondent(client, token).get("/questions/next?count=1")

    payload = response.json()["questions"][0]
    assert payload["type"] == "lane_matchup"
    assert payload["context"] == {"role": "mid", "label": "MID"}
    names = [side["champions"][0]["name"] for side in payload["sides"]]
    assert sorted(names) == ["Syndra", "Zed"]
    a, b = names
    assert [o["label"] for o in payload["options"]] == [
        f"{a} wins hard",
        f"{a} wins slightly",
        "Even",
        f"{b} wins slightly",
        f"{b} wins hard",
    ]


@requires_db
async def test_el_1v1_respeta_el_rol_de_ambos_campeones(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`docs/21-sampler.md` §2.3 — el rol que se muestra lo juegan los dos."""
    row, token = respondent
    await _skip_warmup(db, row)
    _force(monkeypatch, LANE)

    response = await as_respondent(client, token).get("/questions/next?count=10")

    questions = response.json()["questions"]
    assert questions
    for payload in questions:
        role = payload["context"]["role"]
        assert role in {"top", "mid", "adc"}
        ids = [side["champions"][0]["id"] for side in payload["sides"]]
        roles = (
            await db.execute(sa.select(Champion.roles).where(Champion.champion_id.in_(ids)))
        ).scalars()
        assert all(role in {str(r) for r in champion_roles} for champion_roles in roles)


@requires_db
async def test_un_rol_sin_pareja_no_genera_matchups(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§8 — un único top no tiene contra quién jugar, y el 1v1 sólo sale en mid."""
    champions[3].roles = [LaneRole.TOP]
    await db.commit()
    row, token = respondent
    await _skip_warmup(db, row)
    await _only_in_pool(db, champions)
    _force(monkeypatch, LANE)

    response = await as_respondent(client, token).get("/questions/next?count=5")

    questions = response.json()["questions"]
    assert questions
    assert {q["context"]["role"] for q in questions} == {"mid"}


@requires_db
async def test_un_tipo_sin_candidatas_se_saltea(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
) -> None:
    """Sin dimensiones activas el tipo 1 no existe, y el lote sale igual con los otros tipos."""
    await db.execute(sa.update(Dimension).values(is_active=False))
    await db.commit()
    _, token = respondent

    response = await as_respondent(client, token).get("/questions/next?count=3")

    types = [q["type"] for q in response.json()["questions"]]
    assert len(types) == 3
    assert "pairwise_dimension" not in types


@requires_db
@pytest.mark.parametrize("question_type", [PAIRWISE, PEAK, LANE])
async def test_materializar_es_idempotente(
    db: AsyncSession,
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
    question_type: QuestionType,
) -> None:
    """`docs/21-sampler.md` §11 — la misma combinación dos veces es una sola fila.

    Es también la prueba de que la búsqueda compara con `IS NULL` las columnas que el tipo no
    usa: si no lo hiciera, la segunda llamada no encontraría la fila que creó la primera.
    """
    low, high = sorted(c.champion_id for c in champions[:2])
    combination = {
        PAIRWISE: Combination(PAIRWISE, low, champion_b=high, dimension_id=dimension.dimension_id),
        PEAK: Combination(PEAK, low),
        LANE: Combination(LANE, low, champion_b=high, role=LaneRole.MID),
    }[question_type]

    first = await materialize(db, patch.patch_id, combination)
    second = await materialize(db, patch.patch_id, combination)

    assert first.question_id == second.question_id
    rows = (
        await db.execute(
            sa.select(sa.func.count())
            .select_from(Question)
            .where(
                Question.patch_id == patch.patch_id,
                Question.type == question_type,
                Question.champion_a == low,
            )
        )
    ).scalar_one()
    assert rows == 1
