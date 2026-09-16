"""Entrega de preguntas — versión reducida, de la semana 2 a la 4.

**Esto NO es el sampler.** El sampler completo —función de prioridad por escasez, entropía,
cobertura y puentes, exploración con epsilon, honeypots, retests y la regla de variedad— es el
entregable de la semana 5 y está especificado en `docs/21-sampler.md` §10. Acá está sólo lo que
hace falta para que los tipos implementados funcionen de punta a punta:

- tres tipos: `pairwise_dimension`, `peak_timing` y la variante 1v1 de `lane_matchup`, que es el
  orden que fija `docs/20-tipos-de-pregunta.md` §8;
- la composición de la sesión reducida a dos reglas de §7: las tres primeras preguntas de un
  respondedor son de tipo 1 (CA-102), y después el tipo se sortea con los pesos 50/20/15,
  renormalizados sobre los tipos que tienen candidatas;
- sorteo uniforme dentro del tipo, que es literalmente el régimen de arranque en frío que manda
  [ADR-012] mientras una pregunta tiene menos de `sampler.cold_threshold` respuestas — y al
  arrancar el piloto **todas** están en ese caso;
- generación bajo demanda: la pregunta se materializa cuando se la sortea, nunca se precomputa el
  producto cartesiano (RF-111).

Cuando llegue la semana 5, lo que se agrega es la rama de explotación y las reglas de composición
que faltan; esta rama se conserva.
"""

from __future__ import annotations

import random
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models import (
    Champion,
    Dimension,
    LaneRole,
    Patch,
    Question,
    QuestionType,
    Respondent,
    Response,
)
from app.schemas.questions import (
    ChampionRef,
    Help,
    LaneContext,
    LaneMatchupQuestion,
    Option,
    PairwiseDimensionQuestion,
    PeakTimingQuestion,
    QuestionOut,
    Side,
    Slider,
    SliderMark,
    Subject,
)
from app.services import app_settings, question_texts

#: Cuántas preguntas de tipo 1 abren la sesión de un respondedor nuevo: son las más fáciles de
#: entender sin instrucciones (`docs/20-tipos-de-pregunta.md` §7, CA-102).
WARMUP_PAIRWISE: Final = 3

#: La mezcla de `docs/20-tipos-de-pregunta.md` §7, restringida a los tipos que existen.
#: `random.choices` renormaliza sola sobre los disponibles: 50/20/15 da ≈59/24/18 %.
#: En la semana 8 hay que separar por **variante** y no por tipo, porque el 1v1 (15 %) y el
#: 2v2 (5 %) comparten `QuestionType.LANE_MATCHUP`.
TYPE_WEIGHTS: dict[QuestionType, int] = {
    QuestionType.PAIRWISE_DIMENSION: 50,
    QuestionType.PEAK_TIMING: 20,
    QuestionType.LANE_MATCHUP: 15,
}

#: Los roles del 1v1. La jungla no entra: no tiene un oponente fijo con quien intercambiar
#: durante diez minutos (`docs/20-tipos-de-pregunta.md` §4.1).
LANE_1V1_ROLES: Final = (LaneRole.TOP, LaneRole.MID, LaneRole.ADC)

_rng = random.Random()


@dataclass(frozen=True, slots=True)
class Combination:
    """Una pregunta que existe conceptualmente aunque no esté en la base (`21-sampler.md` §2.2).

    Llega ya en forma canónica: `(A,B)` y `(B,A)` son la misma pregunta y el CHECK
    `questions_canonical_order` exige `champion_a < champion_b`.
    """

    type: QuestionType
    champion_a: int
    champion_b: int | None = None
    dimension_id: int | None = None
    role: LaneRole | None = None


@dataclass(frozen=True, slots=True)
class Space:
    """El espacio de combinaciones habilitado (`docs/21-sampler.md` §2.3).

    Se carga una vez por lote: el catálogo son unas decenas de filas y sortear en memoria evita
    una consulta por intento.
    """

    champions: Sequence[Champion]
    dimensions: Sequence[Dimension]
    lanes: Mapping[LaneRole, Sequence[Champion]]

    @classmethod
    def of(cls, champions: Sequence[Champion], dimensions: Sequence[Dimension]) -> Space:
        return cls(champions, dimensions, lane_pools(champions))

    def available_types(self) -> frozenset[QuestionType]:
        """Los tipos que tienen al menos una combinación posible."""
        available: set[QuestionType] = set()
        if len(self.champions) >= 2 and self.dimensions:
            available.add(QuestionType.PAIRWISE_DIMENSION)
        if self.champions:
            available.add(QuestionType.PEAK_TIMING)
        if self.lanes:
            available.add(QuestionType.LANE_MATCHUP)
        return frozenset(available)


def lane_pools(champions: Sequence[Champion]) -> dict[LaneRole, list[Champion]]:
    """Los candidatos del 1v1 por rol, sólo para los roles con al menos dos campeones.

    Un rol con menos de dos no genera preguntas de tipo 3; no es un error, el tipo simplemente
    tiene menos roles donde sortear (`docs/21-sampler.md` §8). Los roles se comparan como texto
    porque el driver puede devolver los elementos del arreglo como `str` y no como `LaneRole`.
    """
    pools: dict[LaneRole, list[Champion]] = {}
    for role in LANE_1V1_ROLES:
        members = [c for c in champions if role.value in {str(r) for r in c.roles}]
        if len(members) >= 2:
            pools[role] = members
    return pools


def choose_type(
    position: int, available: Collection[QuestionType], rng: random.Random
) -> QuestionType | None:
    """El tipo de la pregunta número `position` del respondedor, contando desde cero.

    Lee `TYPE_WEIGHTS` en cada llamada, no al importar: es lo que permite a los tests forzar un
    tipo sin tocar el sorteo.
    """
    if position < WARMUP_PAIRWISE and QuestionType.PAIRWISE_DIMENSION in available:
        return QuestionType.PAIRWISE_DIMENSION
    candidates = [t for t in TYPE_WEIGHTS if t in available]
    if not candidates:
        return None
    return rng.choices(candidates, weights=[TYPE_WEIGHTS[t] for t in candidates])[0]


def _canonical(a: Champion, b: Champion) -> tuple[int, int]:
    low, high = sorted((a.champion_id, b.champion_id))
    return low, high


def draw_combination(
    question_type: QuestionType, space: Space, rng: random.Random
) -> Combination:
    """Sortea una combinación uniforme del tipo, sin enumerar el espacio (`21-sampler.md` §4.4)."""
    match question_type:
        case QuestionType.PAIRWISE_DIMENSION:
            dimension = rng.choice(space.dimensions)
            a, b = rng.sample(list(space.champions), 2)
            low, high = _canonical(a, b)
            return Combination(
                question_type, low, champion_b=high, dimension_id=dimension.dimension_id
            )
        case QuestionType.PEAK_TIMING:
            return Combination(question_type, rng.choice(space.champions).champion_id)
        case QuestionType.LANE_MATCHUP:
            # Primero el rol y después el par: el par tiene que compartir el rol que se muestra.
            role = rng.choice(list(space.lanes))
            a, b = rng.sample(list(space.lanes[role]), 2)
            low, high = _canonical(a, b)
            return Combination(question_type, low, champion_b=high, role=role)
        case _:
            raise ValueError(f"question type {question_type} is not served yet")


async def current_patch(session: AsyncSession) -> Patch | None:
    return (
        await session.execute(sa.select(Patch).where(Patch.is_current))
    ).scalar_one_or_none()


async def _enabled_champions(session: AsyncSession) -> list[Champion]:
    tiers = await app_settings.get(session, "sampler.enabled_pool_tiers", 1)
    return list(
        (
            await session.execute(
                sa.select(Champion)
                .where(Champion.is_active, Champion.pool_tier <= tiers)
                .order_by(Champion.champion_id)
            )
        ).scalars()
    )


async def _active_dimensions(session: AsyncSession) -> list[Dimension]:
    return list(
        (
            await session.execute(
                sa.select(Dimension)
                .where(Dimension.is_active)
                .order_by(Dimension.display_order, Dimension.dimension_id)
            )
        ).scalars()
    )


async def _answered_question_ids(session: AsyncSession, respondent: Respondent) -> set[int]:
    """Las preguntas que este respondedor ya contestó.

    Se excluyen del lote porque `responses_one_per_question` haría fallar el `POST` con 409:
    servirlas sería garantizar un error de ida y vuelta.
    """
    return set(
        (
            await session.execute(
                sa.select(Response.question_id).where(
                    Response.respondent_id == respondent.respondent_id
                )
            )
        )
        .scalars()
        .all()
    )


async def materialize(session: AsyncSession, patch_id: int, combination: Combination) -> Question:
    """Devuelve la pregunta, creándola si es la primera vez que se sortea (RF-111).

    El `ON CONFLICT DO NOTHING` más el `SELECT` posterior es lo que hace la operación segura
    entre peticiones simultáneas: el árbitro es el índice `questions_identity` de la migración,
    con `NULLS NOT DISTINCT`, no el código (`docs/21-sampler.md` §2.2, errata del 16/09).

    La búsqueda compara las nueve columnas de la identidad. Las que el tipo no usa se comparan con
    `IS NULL`: un `= NULL` nunca es verdadero, y sin la comparación explícita un pico de Kayle
    podría confundirse con cualquier otra pregunta que empiece por Kayle.
    """
    columns: tuple[tuple[InstrumentedAttribute[Any], object], ...] = (
        (Question.type, combination.type),
        (Question.patch_id, patch_id),
        (Question.champion_a, combination.champion_a),
        (Question.champion_b, combination.champion_b),
        (Question.champion_c, None),
        (Question.champion_d, None),
        (Question.dimension_id, combination.dimension_id),
        (Question.role, combination.role),
        (Question.duo_ctx, None),
    )
    identity = [
        column.is_(None) if value is None else column == value for column, value in columns
    ]
    existing = (await session.execute(sa.select(Question).where(*identity))).scalar_one_or_none()
    if existing is not None:
        return existing

    await session.execute(
        pg_insert(Question)
        .values(
            type=combination.type,
            patch_id=patch_id,
            champion_a=combination.champion_a,
            champion_b=combination.champion_b,
            dimension_id=combination.dimension_id,
            role=combination.role,
        )
        .on_conflict_do_nothing()
    )
    await session.commit()
    return (await session.execute(sa.select(Question).where(*identity))).scalar_one()


async def _draw_unseen(
    session: AsyncSession,
    patch_id: int,
    question_type: QuestionType,
    space: Space,
    excluded: Collection[int],
    retries: int,
    rng: random.Random,
) -> Question | None:
    """Rechazo con reintento (`docs/21-sampler.md` §5): una pregunta del tipo, no excluida."""
    for _ in range(retries):
        question = await materialize(session, patch_id, draw_combination(question_type, space, rng))
        if question.question_id not in excluded:
            return question
    return None


async def next_batch(
    session: AsyncSession,
    respondent: Respondent,
    count: int,
    rng: random.Random | None = None,
) -> list[QuestionOut]:
    """Sortea hasta `count` preguntas distintas y las devuelve ya renderizadas.

    Un tipo que agota sus reintentos queda descartado **para el resto del lote** y el sorteo sigue
    entre los demás. Puede pasar por mala suerte con un pool chico; el costo es un lote con otra
    mezcla, que es inofensivo. Si se agotan todos, el lote sale más corto y, si queda vacío, la
    interfaz muestra el estado de cola vacía.
    """
    rng = rng or _rng
    patch = await current_patch(session)
    if patch is None:
        return []
    space = Space.of(await _enabled_champions(session), await _active_dimensions(session))
    available = space.available_types()
    if not available:
        return []

    retries = await app_settings.get(session, "sampler.max_rejection_retries", 10)
    answered = await _answered_question_ids(session, respondent)

    chosen: list[Question] = []
    seen: set[int] = set()
    exhausted: set[QuestionType] = set()
    for index in range(count):
        question: Question | None = None
        while question is None:
            question_type = choose_type(
                respondent.answers_count + index, available - exhausted, rng
            )
            if question_type is None:
                break
            question = await _draw_unseen(
                session, patch.patch_id, question_type, space, answered | seen, retries, rng
            )
            if question is None:
                exhausted.add(question_type)
        if question is None:
            break
        seen.add(question.question_id)
        chosen.append(question)

    champions = {c.champion_id: c for c in space.champions}
    dimensions = {d.dimension_id: d for d in space.dimensions}
    return [render(q, champions, dimensions) for q in chosen]


def champion_ref(champion: Champion) -> ChampionRef:
    return ChampionRef(
        id=champion.champion_id,
        key=champion.riot_key,
        name=champion.display_name,
        image_url=champion.image_url,
    )


def role_label(role: LaneRole) -> str:
    """La etiqueta del carril que se muestra sobre los retratos: `TOP`, `MID`, `ADC`."""
    return role.value.upper()


def render(
    question: Question, champions: Mapping[int, Champion], dimensions: Mapping[int, Dimension]
) -> QuestionOut:
    """El enunciado ya compuesto, como exige `docs/12-api.md` §1.1. El cliente no ve plantillas."""
    match question.type:
        case QuestionType.PAIRWISE_DIMENSION:
            assert question.dimension_id is not None
            return render_pairwise(question, dimensions[question.dimension_id], champions)
        case QuestionType.PEAK_TIMING:
            return render_peak(question, champions)
        case QuestionType.LANE_MATCHUP:
            return render_lane(question, champions)
        case _:
            raise ValueError(f"question type {question.type} is not served yet")


def render_pairwise(
    question: Question, dimension: Dimension, champions: Mapping[int, Champion]
) -> PairwiseDimensionQuestion:
    """El texto sale de `dimensions`, no del código: agregar una dimensión es insertar una fila
    (RF-603, CA-601)."""
    assert question.champion_b is not None
    return PairwiseDimensionQuestion(
        question_id=question.question_id,
        prompt=dimension.prompt_en,
        help=Help(label=dimension.label_en, text=dimension.description_en),
        options=[
            Side(key="a", champions=[champion_ref(champions[question.champion_a])]),
            Side(key="b", champions=[champion_ref(champions[question.champion_b])]),
            Side(key="unknown", label=question_texts.UNKNOWN_LABEL, champions=[]),
        ],
    )


def render_peak(question: Question, champions: Mapping[int, Champion]) -> PeakTimingQuestion:
    """Tipo 2. Los textos y la escala son constantes del backend (ADR-018)."""
    champion = champions[question.champion_a]
    return PeakTimingQuestion(
        question_id=question.question_id,
        prompt=question_texts.PEAK_PROMPT.format(name=champion.display_name),
        help=Help(label=question_texts.PEAK_HELP_LABEL, text=question_texts.PEAK_HELP_TEXT),
        subject=Subject(champions=[champion_ref(champion)]),
        slider=Slider(
            min=question_texts.PEAK_MIN,
            max=question_texts.PEAK_MAX,
            step=question_texts.PEAK_STEP,
            default=question_texts.PEAK_DEFAULT,
            unit=question_texts.PEAK_UNIT,
            marks=[SliderMark(at=at, label=label) for at, label in question_texts.PEAK_MARKS],
        ),
    )


def render_lane(question: Question, champions: Mapping[int, Champion]) -> LaneMatchupQuestion:
    """Tipo 3, variante 1v1. La 2v2 —duplas en vez de campeones— llega en la semana 8."""
    assert question.champion_b is not None and question.role is not None
    a = champions[question.champion_a]
    b = champions[question.champion_b]
    role = LaneRole(str(question.role))
    return LaneMatchupQuestion(
        question_id=question.question_id,
        prompt=question_texts.LANE_PROMPT,
        help=Help(label=question_texts.LANE_HELP_LABEL, text=question_texts.LANE_HELP_TEXT),
        context=LaneContext(role=role, label=role_label(role)),
        sides=[
            Side(key="a", champions=[champion_ref(a)]),
            Side(key="b", champions=[champion_ref(b)]),
        ],
        options=[
            Option(key=key, label=template.format(a=a.display_name, b=b.display_name))
            for key, template in question_texts.LANE_OPTION_TEMPLATES.items()
        ],
    )
