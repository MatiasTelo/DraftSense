"""Generación perezosa y render de preguntas (`docs/21-sampler.md` §2 y `docs/12-api.md` §2.3).

Acá está lo que no depende de *cuál* pregunta toca:

- el espacio de combinaciones habilitado (`Space`) y lo que el pool actual admite servir;
- el sorteo uniforme de una combinación sin enumerar el espacio (§4.4);
- la materialización bajo demanda, que nunca precomputa el producto cartesiano (RF-111);
- el render, que manda el enunciado ya compuesto (`docs/12-api.md` §1.1).

La composición de la sesión y la elección de la pregunta —prioridad, exploración, honeypots,
retests, variedad— están en `sampler.py` desde la semana 5.

Se sirven tres tipos: `pairwise_dimension` —desde ADR-022, como un ranking de cinco armado
alrededor de un par ancla (`rankings.py`)—, `peak_timing` y la variante 1v1 de `lane_matchup`,
que es el orden de `docs/20-tipos-de-pregunta.md` §8. La 2v2 y los tipos 4 y 5 llegan en la
semana 8.
"""

from __future__ import annotations

import math
import random
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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
    Ranking,
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

#: Los tipos que el sistema sabe servir y renderizar.
SERVED_TYPES: Final = (
    QuestionType.PAIRWISE_DIMENSION,
    QuestionType.PEAK_TIMING,
    QuestionType.LANE_MATCHUP,
)

#: Cuántos campeones ordena una tarjeta de tipo 1. Con cinco salen C(5, 2) = 10 comparaciones
#: (ADR-022).
RANKING_SIZE: Final = 5

#: Los roles del 1v1. La jungla no entra: no tiene un oponente fijo con quien intercambiar
#: durante diez minutos (`docs/20-tipos-de-pregunta.md` §4.1).
LANE_1V1_ROLES: Final = (LaneRole.TOP, LaneRole.MID, LaneRole.ADC)


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


def _role_names(champion: Champion) -> set[str]:
    """Los roles como texto: el driver puede devolver los elementos del arreglo como `str`."""
    return {str(r) for r in champion.roles}


def lane_pools(champions: Sequence[Champion]) -> dict[LaneRole, list[Champion]]:
    """Los candidatos del 1v1 por rol, sólo para los roles con al menos dos campeones.

    Un rol con menos de dos no genera preguntas de tipo 3; no es un error, el tipo simplemente
    tiene menos roles donde sortear (`docs/21-sampler.md` §8).
    """
    pools: dict[LaneRole, list[Champion]] = {}
    for role in LANE_1V1_ROLES:
        members = [c for c in champions if role.value in _role_names(c)]
        if len(members) >= 2:
            pools[role] = members
    return pools


@dataclass(frozen=True, slots=True)
class Space:
    """El espacio de combinaciones habilitado (`docs/21-sampler.md` §2.3).

    Se carga una vez por lote: el catálogo son unas decenas de filas y sortear en memoria evita
    una consulta por intento.
    """

    champions: Sequence[Champion]
    dimensions: Sequence[Dimension]
    lanes: Mapping[LaneRole, Sequence[Champion]]
    champion_ids: frozenset[int] = field(default_factory=frozenset)
    dimension_ids: frozenset[int] = field(default_factory=frozenset)
    lane_ids: Mapping[LaneRole, frozenset[int]] = field(default_factory=dict)

    @classmethod
    def of(cls, champions: Sequence[Champion], dimensions: Sequence[Dimension]) -> Space:
        lanes = lane_pools(champions)
        return cls(
            champions=champions,
            dimensions=dimensions,
            lanes=lanes,
            champion_ids=frozenset(c.champion_id for c in champions),
            dimension_ids=frozenset(d.dimension_id for d in dimensions),
            lane_ids={
                role: frozenset(c.champion_id for c in members) for role, members in lanes.items()
            },
        )

    def roles_without_pair(self) -> list[LaneRole]:
        """Los roles del 1v1 que este pool no puede servir, para el registro de §8."""
        return [role for role in LANE_1V1_ROLES if role not in self.lanes]

    def available_types(self) -> frozenset[QuestionType]:
        """Los tipos que tienen al menos una combinación posible."""
        available: set[QuestionType] = set()
        if len(self.champions) >= RANKING_SIZE and self.dimensions:
            available.add(QuestionType.PAIRWISE_DIMENSION)
        if self.champions:
            available.add(QuestionType.PEAK_TIMING)
        if self.lanes:
            available.add(QuestionType.LANE_MATCHUP)
        return frozenset(available)

    def admits(self, question: Question) -> bool:
        """Si el pool actual todavía puede servir esta pregunta ya materializada.

        Una pregunta se generó con el pool de ese momento. Si después un campeón bajó de tier,
        una dimensión se desactivó o un campeón dejó de tener el rol (ADR-019), la fila sigue en
        la base —y sus respuestas siguen valiendo— pero no se vuelve a mostrar (21 §8).
        """
        if question.type not in SERVED_TYPES:
            return False
        members = [c for c in (question.champion_a, question.champion_b) if c is not None]
        if question.champion_c is not None or question.champion_d is not None:
            # La variante 2v2 del tipo 3 se sirve desde la semana 8.
            return False
        if not all(c in self.champion_ids for c in members):
            return False
        if question.dimension_id is not None and question.dimension_id not in self.dimension_ids:
            return False
        if question.type is QuestionType.PAIRWISE_DIMENSION and question.dimension_id is None:
            return False
        if question.type is QuestionType.LANE_MATCHUP:
            if question.role is None:
                return False
            lane = self.lane_ids.get(LaneRole(str(question.role)))
            return lane is not None and all(c in lane for c in members)
        return True


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
            # Primero el rol y después el par, que tiene que compartir el rol que se muestra. El
            # rol se pesa por su cantidad de pares (errata de §4.4 del 16/09): con un rol
            # uniforme, un par del rol más chico saldría más seguido que uno del más grande.
            roles = list(space.lanes)
            weights = [math.comb(len(space.lanes[role]), 2) for role in roles]
            role = rng.choices(roles, weights=weights)[0]
            a, b = rng.sample(list(space.lanes[role]), 2)
            low, high = _canonical(a, b)
            return Combination(question_type, low, champion_b=high, role=role)
        case _:
            raise ValueError(f"question type {question_type} is not served yet")


async def current_patch(session: AsyncSession) -> Patch | None:
    return (
        await session.execute(sa.select(Patch).where(Patch.is_current))
    ).scalar_one_or_none()


async def enabled_champions(session: AsyncSession) -> list[Champion]:
    """Los campeones activos dentro de `sampler.enabled_pool_tiers` (ADR-006)."""
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


async def active_dimensions(session: AsyncSession) -> list[Dimension]:
    return list(
        (
            await session.execute(
                sa.select(Dimension)
                .where(Dimension.is_active)
                .order_by(Dimension.display_order, Dimension.dimension_id)
            )
        ).scalars()
    )


async def load_space(session: AsyncSession) -> Space:
    return Space.of(await enabled_champions(session), await active_dimensions(session))


async def answered_question_ids(session: AsyncSession, respondent_id: uuid.UUID) -> set[int]:
    """Las preguntas que este respondedor ya contestó, en una sola consulta por lote (§5).

    Se excluyen del lote porque `responses_one_per_question` haría fallar el `POST` con 409:
    servirlas sería garantizar un error de ida y vuelta. La única excepción es el retest, que
    sale de su propio camino.
    """
    return set(
        (
            await session.execute(
                sa.select(Response.question_id).where(Response.respondent_id == respondent_id)
            )
        )
        .scalars()
        .all()
    )


def identity(combination: Combination, patch_id: int) -> list[sa.ColumnElement[bool]]:
    """Las nueve columnas de `questions_identity`, con `IS NULL` en las que el tipo no usa.

    Un `= NULL` nunca es verdadero: sin la comparación explícita, un pico de Kayle podría
    confundirse con cualquier otra pregunta que empiece por Kayle.
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
    return [column.is_(None) if value is None else column == value for column, value in columns]


def _values(combination: Combination, patch_id: int) -> dict[str, Any]:
    return {
        "type": combination.type,
        "patch_id": patch_id,
        "champion_a": combination.champion_a,
        "champion_b": combination.champion_b,
        "dimension_id": combination.dimension_id,
        "role": combination.role,
    }


async def materialize(session: AsyncSession, patch_id: int, combination: Combination) -> Question:
    """Devuelve la pregunta, creándola si es la primera vez que se sortea (RF-111).

    El `ON CONFLICT DO NOTHING` más el `SELECT` posterior es lo que hace la operación segura
    entre peticiones simultáneas: el árbitro es el índice `questions_identity` de la migración,
    con `NULLS NOT DISTINCT`, no el código (`docs/21-sampler.md` §2.2, errata del 16/09).
    """
    conditions = identity(combination, patch_id)
    existing = (await session.execute(sa.select(Question).where(*conditions))).scalar_one_or_none()
    if existing is not None:
        return existing

    await session.execute(
        pg_insert(Question).values(_values(combination, patch_id)).on_conflict_do_nothing()
    )
    await session.commit()
    return (await session.execute(sa.select(Question).where(*conditions))).scalar_one()


async def materialize_many(
    session: AsyncSession, patch_id: int, combinations: Sequence[Combination]
) -> dict[Combination, Question]:
    """`materialize` para muchas combinaciones del tipo 1 de una vez. No hace commit.

    Lo usan `check_graph_connectivity`, que en el arranque crea cientos de puentes, y el registro
    de un ranking, que necesita sus diez pares (ADR-022): de a uno serían cuatro idas a la base por
    pregunta. Un solo `INSERT … ON CONFLICT DO NOTHING` y una
    sola búsqueda por tupla dan el mismo resultado con el mismo árbitro, el índice
    `questions_identity`.
    """
    unique = list(dict.fromkeys(combinations))
    if not unique:
        return {}
    if any(c.type is not QuestionType.PAIRWISE_DIMENSION or c.role is not None for c in unique):
        raise ValueError("materialize_many only handles pairwise_dimension combinations")
    await session.execute(
        pg_insert(Question)
        .values([_values(c, patch_id) for c in unique])
        .on_conflict_do_nothing()
    )
    keys = [(c.champion_a, c.champion_b, c.dimension_id) for c in unique]
    rows = (
        await session.execute(
            sa.select(Question).where(
                Question.type == QuestionType.PAIRWISE_DIMENSION,
                Question.patch_id == patch_id,
                Question.champion_c.is_(None),
                Question.champion_d.is_(None),
                Question.role.is_(None),
                Question.duo_ctx.is_(None),
                sa.tuple_(Question.champion_a, Question.champion_b, Question.dimension_id).in_(
                    keys
                ),
            )
        )
    ).scalars()
    by_key = {(q.champion_a, q.champion_b, q.dimension_id): q for q in rows}
    return {c: by_key[(c.champion_a, c.champion_b, c.dimension_id)] for c in unique}


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
    question: Question,
    champions: Mapping[int, Champion],
    dimensions: Mapping[int, Dimension],
    ranking: Ranking | None = None,
) -> QuestionOut:
    """El enunciado ya compuesto, como exige `docs/12-api.md` §1.1. El cliente no ve plantillas.

    Una pregunta de tipo 1 se sirve como el ancla de `ranking` (ADR-022), y sin él no se puede
    renderizar.
    """
    match question.type:
        case QuestionType.PAIRWISE_DIMENSION:
            assert question.dimension_id is not None and ranking is not None
            return render_ranking(ranking, dimensions[question.dimension_id], champions)
        case QuestionType.PEAK_TIMING:
            return render_peak(question, champions)
        case QuestionType.LANE_MATCHUP:
            return render_lane(question, champions)
        case _:
            raise ValueError(f"question type {question.type} is not served yet")


def render_ranking(
    ranking: Ranking, dimension: Dimension, champions: Mapping[int, Champion]
) -> PairwiseDimensionQuestion:
    """Tipo 1, el ranking de cinco (ADR-022). Los campeones van en el orden guardado, que es
    aleatorio. El enunciado sale de `dimensions`, no del código: agregar una dimensión es insertar
    una fila (RF-603, CA-601)."""
    return PairwiseDimensionQuestion(
        question_id=ranking.anchor_question_id,
        ranking_id=ranking.ranking_id,
        prompt=dimension.prompt_en,
        instruction=question_texts.RANKING_INSTRUCTION,
        help=Help(label=dimension.label_en, text=dimension.description_en),
        champions=[champion_ref(champions[c]) for c in ranking.champions],
        unknown_label=question_texts.UNKNOWN_LABEL,
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
