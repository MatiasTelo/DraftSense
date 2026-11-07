"""La semana 8: la variante 2v2 del tipo 3, el tipo 4, el tipo 5 y el español.

Criterios de `docs/03-criterios-aceptacion.md`: CA-105, CA-107, CA-108, CA-206, CA-207 (cambiado
por ADR-027) y CA-214, más las precisiones del 29/10 de 12 §2.4, 21 §3.2 y §3.3 y 22 §4 y §5.2.

Como los demás, arman su propio pool y su propio catálogo de atributos dentro de la transacción
del test, para pasar igual contra la base vacía de CI y contra una con los seeds cargados.
"""

from __future__ import annotations

import itertools
import random
import re
from collections import Counter
from dataclasses import fields
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Champion,
    DuoContext,
    LaneRole,
    Patch,
    Question,
    QuestionType,
    Respondent,
    Trait,
)
from app.services import question_stats, question_texts, questions, responses, sessions
from app.services import sampler as sampler_service
from app.services.degenerate import HistoryRow, count
from app.services.questions import (
    DUO_ROLES,
    DuoPool,
    Space,
    Variant,
    canonical_duos,
    draw_combination,
    render_bot_lane,
    render_synergy,
    render_traits,
)
from tests.conftest import (
    FAR,
    add_response,
    as_respondent,
    make_champions,
    make_dimensions,
    requires_db,
    restrict_pool,
    set_setting,
)

ADC, SUPPORT, TOP, JUNGLE, MID = (
    LaneRole.ADC,
    LaneRole.SUPPORT,
    LaneRole.TOP,
    LaneRole.JUNGLE,
    LaneRole.MID,
)


def _champion(champion_id: int, roles: list[LaneRole], tier: int = 1) -> Champion:
    return Champion(
        champion_id=champion_id,
        riot_key=f"C{champion_id}",
        riot_name=f"Champ {champion_id}",
        display_name=f"Champ {champion_id}",
        roles=roles,
        image_url=f"https://example.invalid/{champion_id}.png",
        patch_first_seen=1,
        pool_tier=tier,
    )


def _trait(trait_id: int, code: str, label_es: str | None = None) -> Trait:
    return Trait(
        trait_id=trait_id,
        code=code,
        label_en=code.title(),
        description_en=f"What {code} means.",
        label_es=label_es,
        description_es=None,
        display_order=trait_id,
    )


# ------------------------------------------------------------------------- duplas, sin base


def _brute_pairs(pool: DuoPool) -> int:
    duos = [
        ((x, pool.roles[0]), (y, pool.roles[1])) for x in pool.first for y in pool.second if x != y
    ]
    return sum(
        1
        for one, two in itertools.combinations(duos, 2)
        if not {c for c, _ in one} & {c for c, _ in two}
    )


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ((1, 2, 3), (4, 5, 6)),
        ((1, 2, 3, 4), (3, 4, 5)),  # dos campeones con los dos roles, como Xerath y Seraphine
        ((1, 2), (1, 2)),
        ((1,), (2,)),
    ],
)
def test_los_pares_de_duplas_se_cuentan_sin_enumerar(
    first: tuple[int, ...], second: tuple[int, ...]
) -> None:
    pool = DuoPool(DuoContext.BOT, first, second)
    assert pool.pair_count() == _brute_pairs(pool)


def test_la_dupla_canonica_conserva_los_roles() -> None:
    """ADR-026 — el orden canónico es por id y los roles viajan con su campeón."""
    combination = canonical_duos(
        QuestionType.DUO_SYNERGY,
        DuoContext.BOT,
        ((9, ADC), (4, SUPPORT)),
        ((7, SUPPORT), (2, ADC)),
    )
    assert (combination.champion_a, combination.role_a) == (2, ADC)
    assert (combination.champion_b, combination.role_b) == (7, SUPPORT)
    assert (combination.champion_c, combination.role_c) == (4, SUPPORT)
    assert (combination.champion_d, combination.role_d) == (9, ADC)


def _duo_space() -> Space:
    champions = [
        *[_champion(i, [ADC]) for i in range(1, 5)],
        *[_champion(i, [SUPPORT]) for i in range(5, 9)],
        _champion(9, [ADC, SUPPORT]),
        *[_champion(i, [TOP]) for i in range(10, 13)],
        *[_champion(i, [MID]) for i in range(13, 16)],
        *[_champion(i, [JUNGLE]) for i in range(16, 19)],
        _champion(19, [MID, JUNGLE]),
        # Tier 2: entra al 2v2 si el tier está habilitado, nunca al tipo 4.
        _champion(20, [ADC], tier=2),
        _champion(21, [SUPPORT], tier=2),
    ]
    return Space.of(champions, [])


@pytest.mark.parametrize("variant", [Variant.LANE_2V2, Variant.DUO_SYNERGY])
def test_las_duplas_sorteadas_son_validas(variant: Variant) -> None:
    """CA-105 y 21 §2.3 — cuatro distintos, dos duplas del mismo contexto con sus dos roles."""
    space = _duo_space()
    roles = {c.champion_id: {LaneRole(str(r)) for r in c.roles} for c in space.champions}
    rng = random.Random(8)
    for _ in range(500):
        combination = draw_combination(variant, space, rng)
        duos = questions.duos_of(combination)
        assert duos is not None and combination.duo_ctx is not None
        members = [c for duo in duos for c, _ in duo]
        assert len(set(members)) == 4
        assert combination.champion_a < combination.champion_b
        assert combination.champion_c is not None and combination.champion_d is not None
        assert combination.champion_c < combination.champion_d
        assert combination.champion_a < combination.champion_c
        for duo in duos:
            assert {role for _, role in duo} == set(DUO_ROLES[combination.duo_ctx])
            for champion, role in duo:
                assert role in roles[champion]
        if variant is Variant.LANE_2V2:
            assert combination.type is QuestionType.LANE_MATCHUP
            assert combination.duo_ctx is DuoContext.BOT
        else:
            assert combination.type is QuestionType.DUO_SYNERGY
            assert not {20, 21} & set(members)


def test_el_contexto_del_tipo_4_se_pesa_por_sus_pares() -> None:
    """20 §5, nota del 29/10 — proporcional a los pares de duplas válidas de cada contexto."""
    space = _duo_space()
    rng = random.Random(21)
    draws = Counter(
        draw_combination(Variant.DUO_SYNERGY, space, rng).duo_ctx for _ in range(20_000)
    )
    total = sum(pool.pair_count() for pool in space.synergy.values())
    for context, pool in space.synergy.items():
        assert draws[context] / 20_000 == pytest.approx(pool.pair_count() / total, abs=0.02)


def _duo_question(question_type: QuestionType, context: DuoContext, **roles: Any) -> Question:
    return Question(
        question_id=5,
        type=question_type,
        patch_id=1,
        champion_a=1,
        champion_b=2,
        champion_c=3,
        champion_d=4,
        duo_ctx=context,
        **roles,
    )


def test_ca108_cada_lado_respeta_el_orden_de_roles() -> None:
    """CA-108 — el jungla va segundo aunque sea `champion_a`."""
    champions = {i: _champion(i, [MID, JUNGLE]) for i in range(1, 5)}
    question = _duo_question(
        QuestionType.DUO_SYNERGY,
        DuoContext.MID_JUNGLE,
        role_a=JUNGLE,
        role_b=MID,
        role_c=MID,
        role_d=JUNGLE,
    )
    rendered = render_synergy(question, champions)

    assert [side.key for side in rendered.sides] == ["pair_1", "pair_2"]
    assert [c.id for c in rendered.sides[0].champions] == [2, 1]
    assert [c.id for c in rendered.sides[1].champions] == [3, 4]
    assert [o.key for o in rendered.options] == ["pair_1", "similar", "pair_2"]
    assert rendered.context.label == "MID + JUNGLE"


def test_el_2v2_lleva_contexto_de_dupla_y_etiquetas_de_pareja() -> None:
    champions = {i: _champion(i, [ADC, SUPPORT]) for i in range(1, 5)}
    question = _duo_question(
        QuestionType.LANE_MATCHUP,
        DuoContext.BOT,
        role_a=ADC,
        role_b=SUPPORT,
        role_c=SUPPORT,
        role_d=ADC,
    )
    rendered = render_bot_lane(question, champions).model_dump()

    assert rendered["context"] == {"duo_context": "bot", "label": "BOT"}
    assert [s["key"] for s in rendered["sides"]] == ["a", "b"]
    assert [c["id"] for c in rendered["sides"][1]["champions"]] == [4, 3]
    assert rendered["options"][0] == {"key": "a_strong", "label": "Top pair wins hard"}

    spanish = render_bot_lane(question, champions, "es")
    assert spanish.prompt == "¿Qué dupla gana la bot lane al minuto 10?"
    assert spanish.options[-1].label == "La dupla de abajo gana claramente"


def test_el_tipo_5_trae_los_atributos_y_cae_al_ingles() -> None:
    """ADR-028 — sin texto en español, sale el inglés: nunca una etiqueta vacía."""
    champion = _champion(1, [TOP])
    question = Question(
        question_id=9, type=QuestionType.TRAIT_MULTISELECT, patch_id=1, champion_a=1
    )
    traits = [_trait(1, "engage", "Engage"), _trait(2, "poke")]

    rendered = render_traits(question, {1: champion}, traits, "es")

    assert rendered.prompt == "¿En qué se destaca Champ 1?"
    assert rendered.subtitle == "Elige todos los que correspondan."
    assert rendered.help is None
    assert [(t.code, t.label) for t in rendered.traits] == [("engage", "Engage"), ("poke", "Poke")]
    assert rendered.traits[0].help == "What engage means."


def test_los_dos_idiomas_tienen_los_mismos_textos() -> None:
    """ADR-028 — mismas claves y mismos marcadores de sustitución en inglés y en español."""

    def markers(value: object) -> object:
        if isinstance(value, str):
            return sorted(re.findall(r"\{(\w+)\}", value))
        if isinstance(value, dict):
            return {k: markers(v) for k, v in value.items()}
        if isinstance(value, tuple):
            return [markers(v) for v in value]
        return value

    for spec in fields(question_texts.Texts):
        english = getattr(question_texts.EN, spec.name)
        spanish = getattr(question_texts.ES, spec.name)
        assert markers(english) == markers(spanish), spec.name


# ---------------------------------------------------------------- estadísticas, sin base


def test_la_entropia_del_tipo_4_es_de_tres_resultados() -> None:
    parejo = question_stats.synergy_entropy({"pair_1": 5, "similar": 5, "pair_2": 5})
    assert parejo == Decimal("1.0000")
    assert question_stats.synergy_entropy({"pair_1": 9}) == Decimal("0.0000")
    assert question_stats.synergy_entropy({}) is None


def test_la_entropia_del_tipo_5_promedia_los_atributos() -> None:
    """21 §3.2, nota del 29/10 — mitad y mitad en uno, unánime en el otro: (1 + 0) / 2."""
    counts = {"engage": 5, "poke": 10, "_total": 10}
    assert question_stats.traits_entropy(counts, ["engage", "poke"]) == Decimal("0.5000")
    assert question_stats.exposure(QuestionType.TRAIT_MULTISELECT, counts) == 10
    assert question_stats.traits_entropy({}, ["engage"]) is None


def test_el_straightlining_del_tipo_4_es_propio_y_el_5_no_cuenta() -> None:
    """22 §5.2, nota del 29/10."""
    synergy = [HistoryRow(QuestionType.DUO_SYNERGY, {"choice": "pair_1"}, 3000) for _ in range(8)]
    traits = [
        HistoryRow(QuestionType.TRAIT_MULTISELECT, {"traits": ["engage"]}, 3000) for _ in range(8)
    ]
    assert count(synergy, 800, 8) == (0, 1)
    assert count(traits, 800, 8) == (0, 0)
    # El 1v1 y el 2v2 comparten subsecuencia: cuatro y cuatro hacen ocho.
    lane = [HistoryRow(QuestionType.LANE_MATCHUP, {"choice": "even"}, 3000) for _ in range(8)]
    assert count(lane, 800, 8) == (0, 1)


# ------------------------------------------------------------------------------- con base


async def _traits(db: AsyncSession, codes: list[str]) -> list[Trait]:
    """Deja activos sólo estos atributos, creándolos si hace falta."""
    await db.execute(sa.update(Trait).values(is_active=False))
    found: list[Trait] = []
    for index, code in enumerate(codes):
        row = (await db.execute(sa.select(Trait).where(Trait.code == code))).scalar_one_or_none()
        if row is None:
            row = Trait(
                code=code,
                label_en=code.title(),
                description_en=f"What {code} means.",
                display_order=90 + index,
            )
            db.add(row)
        row.is_active = True
        found.append(row)
    await db.commit()
    return found


async def _duo_pool(db: AsyncSession, patch: Patch) -> list[Champion]:
    bot = await make_champions(db, patch, 3, roles=[ADC], prefix="Adc")
    bot += await make_champions(db, patch, 3, roles=[SUPPORT], prefix="Sup")
    bot += await make_champions(db, patch, 2, roles=[ADC, SUPPORT], prefix="Flex")
    return bot


async def _question_of(db: AsyncSession, patch: Patch, variant: Variant, space: Space) -> Question:
    combination = draw_combination(variant, space, random.Random(4))
    return await questions.materialize(db, patch.patch_id, combination)


@requires_db
async def test_ca214_la_dupla_guarda_el_rol_de_cada_campeon(db: AsyncSession, patch: Patch) -> None:
    flex = await make_champions(db, patch, 2, roles=[ADC, SUPPORT], prefix="Xs")
    others = await make_champions(db, patch, 2, roles=[ADC, SUPPORT], prefix="Ot")
    x, s = (c.champion_id for c in flex)
    o1, o2 = (c.champion_id for c in others)

    one = canonical_duos(
        QuestionType.DUO_SYNERGY,
        DuoContext.BOT,
        ((x, SUPPORT), (s, ADC)),
        ((o1, ADC), (o2, SUPPORT)),
    )
    swapped = canonical_duos(
        QuestionType.DUO_SYNERGY,
        DuoContext.BOT,
        ((x, ADC), (s, SUPPORT)),
        ((o1, ADC), (o2, SUPPORT)),
    )
    first = await questions.materialize(db, patch.patch_id, one)
    second = await questions.materialize(db, patch.patch_id, swapped)

    assert first.question_id != second.question_id
    assert {(first.champion_a, first.role_a), (first.champion_b, first.role_b)} == {
        (x, SUPPORT),
        (s, ADC),
    }
    assert (await questions.materialize(db, patch.patch_id, one)).question_id == first.question_id

    with pytest.raises(IntegrityError):
        db.add(
            Question(
                type=QuestionType.DUO_SYNERGY,
                patch_id=patch.patch_id,
                champion_a=min(x, s),
                champion_b=max(x, s),
                champion_c=min(o1, o2),
                champion_d=max(o1, o2),
                duo_ctx=DuoContext.BOT,
                role_a=ADC,
                role_b=ADC,
                role_c=ADC,
                role_d=SUPPORT,
            )
        )
        await db.commit()
    await db.rollback()


async def _post(
    client: AsyncClient, token: str, question: Question, answer: dict[str, Any]
) -> dict[str, Any]:
    response = await as_respondent(client, token).post(
        "/responses",
        json={"question_id": question.question_id, "answer": answer, "response_time_ms": 3000},
    )
    return {"status": response.status_code, "body": response.json()}


@requires_db
async def test_ca207_la_lista_vacia_de_traits_se_rechaza(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
) -> None:
    """CA-207 desde ADR-027 — `400` en la API y el CHECK en la base."""
    row, token = respondent
    [champion] = await make_champions(db, patch, 1, prefix="Tv")
    await _traits(db, ["tvalpha"])
    question = Question(
        type=QuestionType.TRAIT_MULTISELECT,
        champion_a=champion.champion_id,
        patch_id=patch.patch_id,
    )
    db.add(question)
    await db.commit()

    result = await _post(client, token, question, {"traits": []})

    assert result["status"] == 400
    assert result["body"]["error"]["code"] == "answer_shape_mismatch"
    with pytest.raises(IntegrityError):
        await add_response(db, row, question, {"traits": []})
    await db.rollback()


@requires_db
async def test_ca206_un_atributo_inexistente_se_rechaza(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
) -> None:
    _, token = respondent
    [champion] = await make_champions(db, patch, 1, prefix="Tu")
    await _traits(db, ["tualpha"])
    question = Question(
        type=QuestionType.TRAIT_MULTISELECT,
        champion_a=champion.champion_id,
        patch_id=patch.patch_id,
    )
    db.add(question)
    await db.commit()

    result = await _post(client, token, question, {"traits": ["tualpha", "nope_code"]})

    assert result["status"] == 400
    assert result["body"]["error"]["code"] == "unknown_trait_code"
    ok = await _post(client, token, question, {"traits": ["tualpha"]})
    assert ok["status"] == 201


async def _ready(db: AsyncSession, respondent: Respondent, champions: list[Champion]) -> None:
    await restrict_pool(db, champions)
    respondent.answers_count = 3
    respondent.next_honeypot_at = FAR
    respondent.next_retest_at = FAR
    await db.commit()


@requires_db
@pytest.mark.parametrize("variant", [Variant.LANE_2V2, Variant.DUO_SYNERGY, Variant.TRAITS])
async def test_ca105_cada_variante_nueva_se_sirve_por_http(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    monkeypatch: pytest.MonkeyPatch,
    variant: Variant,
) -> None:
    """CA-105 — las duplas llegan con dos campeones por lado, los cuatro distintos."""
    row, token = respondent
    pool = await _duo_pool(db, patch)
    await _traits(db, ["twalpha", "twbeta"])
    await _ready(db, row, pool)
    monkeypatch.setattr(sampler_service, "TYPE_WEIGHTS", {variant: 1})

    response = await as_respondent(client, token).get("/questions/next?count=3")

    assert response.status_code == 200
    items = response.json()["questions"]
    assert items
    for item in items:
        assert item["type"] == variant.question_type.value
        if variant is Variant.TRAITS:
            assert [t["code"] for t in item["traits"]] == ["twalpha", "twbeta"]
            assert item["help"] is None
            continue
        sides = item["sides"]
        assert all(len(side["champions"]) == 2 for side in sides)
        assert len({c["id"] for side in sides for c in side["champions"]}) == 4
        assert item["context"]["duo_context"] == "bot"
        assert "role" not in item["context"]


@requires_db
async def test_ca107_la_pregunta_llega_en_el_idioma_pedido(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row, token = respondent
    champions = await make_champions(db, patch, 10, prefix="Es")
    [dimension] = await make_dimensions(db, ["esdim"])
    dimension.prompt_es = "¿Quién escala mejor?"
    dimension.label_es = "Scaling"
    dimension.description_es = "Cuánto más fuerte se vuelve con oro y niveles."
    await restrict_pool(db, champions, [dimension])
    row.next_honeypot_at = FAR
    row.next_retest_at = FAR
    await db.commit()

    http = as_respondent(client, token)
    spanish = (await http.get("/questions/next?count=1&lang=es")).json()["questions"][0]
    assert spanish["prompt"] == "¿Quién escala mejor?"
    assert spanish["unknown_label"] == "No estoy seguro"

    english = (await http.get("/questions/next?count=1")).json()["questions"][0]
    assert english["prompt"] == "Who has more esdim?"

    wrong = await http.get("/questions/next?count=1&lang=fr")
    assert wrong.status_code == 400
    assert wrong.json()["error"] == {
        "code": "invalid_parameter",
        "message": "lang must be one of: en, es",
        "field": "lang",
    }


@requires_db
async def test_el_tipo_5_cuenta_atributos_y_respuestas(
    db: AsyncSession, patch: Patch, respondent: tuple[Respondent, str]
) -> None:
    """11 §3.8, nota del 29/10 — un conteo por atributo más `_total`."""
    row, _ = respondent
    [champion] = await make_champions(db, patch, 1, prefix="Tc")
    await restrict_pool(db, [champion])
    await _traits(db, ["tcalpha", "tcbeta"])
    question = Question(
        type=QuestionType.TRAIT_MULTISELECT,
        champion_a=champion.champion_id,
        patch_id=patch.patch_id,
    )
    db.add(question)
    await db.commit()
    others = [(await sessions.create(db, f"huella-tc-{i}"))[0] for i in range(2)]
    await add_response(db, row, question, {"traits": ["tcalpha"]})
    await add_response(db, others[0], question, {"traits": ["tcalpha", "tcbeta"]})
    await add_response(db, others[1], question, {"traits": ["tcbeta"]})

    await question_stats.refresh(db)
    await db.refresh(question)

    assert question.answer_counts == {"tcalpha": 2, "tcbeta": 2, "_total": 3}
    assert question.exposure_count == 3
    assert question.entropy is not None


@requires_db
async def test_el_feedback_del_tipo_5_es_por_atributo(db: AsyncSession, patch: Patch) -> None:
    """12 §2.4, nota del 29/10 — fracción por atributo y acuerdo con la mayoría."""
    await _traits(db, ["tfalpha", "tfbeta", "tfgamma"])
    await set_setting(db, "sampler.consensus_threshold", 4)
    question = Question(
        question_id=0,
        type=QuestionType.TRAIT_MULTISELECT,
        champion_a=1,
        patch_id=patch.patch_id,
        answer_counts={"tfalpha": 3, "tfbeta": 1, "_total": 4},
    )

    feedback = await responses.build_feedback(db, question, {"traits": ["tfalpha", "tfbeta"]})

    assert feedback is not None
    assert feedback.trait_shares == {"tfalpha": 0.75, "tfbeta": 0.25, "tfgamma": 0.0}
    # Coincide en tfalpha (marcó, 75 %) y en tfgamma (no marcó, 0 %); no en tfbeta.
    assert (feedback.traits_agreed, feedback.traits_compared, feedback.sample_size) == (2, 3, 4)
    assert feedback.consensus is None
    dumped = feedback.model_dump()
    assert "consensus" not in dumped and "pairs_agreed" not in dumped

    few = Question(
        question_id=0,
        type=QuestionType.TRAIT_MULTISELECT,
        champion_a=1,
        patch_id=patch.patch_id,
        answer_counts={"tfalpha": 3, "_total": 3},
    )
    assert await responses.build_feedback(db, few, {"traits": ["tfalpha"]}) is None


@requires_db
async def test_la_cobertura_del_2v2_va_por_campeon_en_bot(
    db: AsyncSession, patch: Patch, respondent: tuple[Respondent, str]
) -> None:
    """21 §3.3, nota del 29/10 — la celda es (campeón, `bot`), aparte del 1v1."""
    row, _ = respondent
    pool = await _duo_pool(db, patch)
    await restrict_pool(db, pool)
    await _traits(db, ["tkalpha"])
    space = await questions.load_space(db)
    question = await _question_of(db, patch, Variant.LANE_2V2, space)
    await add_response(db, row, question, {"choice": "even"})

    result = await question_stats.refresh(db)
    await db.refresh(question)

    assert result.coverage_medians["lane_2v2"] is not None
    assert question.answer_counts == {"even": 1}
    assert question.entropy == Decimal("0.0000")
