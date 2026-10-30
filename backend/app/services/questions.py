"""Generación perezosa y render de preguntas (`docs/21-sampler.md` §2 y `docs/12-api.md` §2.3).

Acá está lo que no depende de *cuál* pregunta toca:

- el espacio de combinaciones habilitado (`Space`) y lo que el pool actual admite servir;
- el sorteo uniforme de una combinación sin enumerar el espacio (§4.4);
- la materialización bajo demanda, que nunca precomputa el producto cartesiano (RF-111);
- el render, que manda el enunciado ya compuesto y en el idioma pedido (`docs/12-api.md` §1.1,
  ADR-028).

La composición de la sesión y la elección de la pregunta —prioridad, exploración, honeypots,
retests, variedad— están en `sampler.py`.

Desde la semana 8 se sirven los cinco tipos, en seis **variantes**: el tipo 3 tiene el 1v1 de
línea y el 2v2 de bot, que comparten `QuestionType` pero no su peso en la mezcla
(`docs/20-tipos-de-pregunta.md` §7). Las preguntas de duplas guardan el rol de cada campeón
([ADR-026]).
"""

from __future__ import annotations

import math
import random
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models import (
    Champion,
    Dimension,
    DuoContext,
    LaneRole,
    Patch,
    Question,
    QuestionType,
    Ranking,
    Response,
    Trait,
)
from app.schemas.questions import (
    ChampionRef,
    DuoContextOut,
    DuoSynergyQuestion,
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
    TraitMultiselectQuestion,
    TraitOption,
)
from app.services import app_settings, question_texts
from app.services.question_texts import DEFAULT_LANG, Lang

#: Los tipos que el sistema sabe servir y renderizar.
SERVED_TYPES: Final = (
    QuestionType.PAIRWISE_DIMENSION,
    QuestionType.PEAK_TIMING,
    QuestionType.LANE_MATCHUP,
    QuestionType.DUO_SYNERGY,
    QuestionType.TRAIT_MULTISELECT,
)


class Variant(StrEnum):
    """Lo que la mezcla de la sesión distingue: los cinco tipos, con el tipo 3 partido en dos.

    La regla de variedad, en cambio, mira el tipo (`question_type`): tres seguidas entre 1v1 y 2v2
    ya son tres del tipo 3 (`docs/21-sampler.md` §6, nota del 29/10).
    """

    PAIRWISE = "pairwise_dimension"
    PEAK = "peak_timing"
    LANE_1V1 = "lane_1v1"
    LANE_2V2 = "lane_2v2"
    DUO_SYNERGY = "duo_synergy"
    TRAITS = "trait_multiselect"

    @property
    def question_type(self) -> QuestionType:
        return _VARIANT_TYPES[self]


_VARIANT_TYPES: Final = {
    Variant.PAIRWISE: QuestionType.PAIRWISE_DIMENSION,
    Variant.PEAK: QuestionType.PEAK_TIMING,
    Variant.LANE_1V1: QuestionType.LANE_MATCHUP,
    Variant.LANE_2V2: QuestionType.LANE_MATCHUP,
    Variant.DUO_SYNERGY: QuestionType.DUO_SYNERGY,
    Variant.TRAITS: QuestionType.TRAIT_MULTISELECT,
}


def variant_of(question: Question) -> Variant:
    """La variante de una pregunta ya materializada: el 2v2 es el `lane_matchup` con cuatro."""
    question_type = QuestionType(question.type)
    if question_type is QuestionType.LANE_MATCHUP:
        return Variant.LANE_2V2 if question.champion_c is not None else Variant.LANE_1V1
    return next(v for v, t in _VARIANT_TYPES.items() if t is question_type)


#: Cuántos campeones ordena una tarjeta de tipo 1. Con cinco salen C(5, 2) = 10 comparaciones
#: (ADR-022).
RANKING_SIZE: Final = 5

#: Los roles del 1v1. La jungla no entra: no tiene un oponente fijo con quien intercambiar
#: durante diez minutos (`docs/20-tipos-de-pregunta.md` §4.1).
LANE_1V1_ROLES: Final = (LaneRole.TOP, LaneRole.MID, LaneRole.ADC)

#: Los dos roles de cada contexto de dupla, en el orden en que se muestran (ADR-026): primero el
#: adc, el top o el mid; después el support o el jungla.
DUO_ROLES: Final[dict[DuoContext, tuple[LaneRole, LaneRole]]] = {
    DuoContext.BOT: (LaneRole.ADC, LaneRole.SUPPORT),
    DuoContext.TOP_JUNGLE: (LaneRole.TOP, LaneRole.JUNGLE),
    DuoContext.MID_JUNGLE: (LaneRole.MID, LaneRole.JUNGLE),
}

#: El tipo 4 se restringe al tier 1, cualquiera sea el pool habilitado (20 §5, nota del 29/10):
#: el espacio de duplas es demasiado grande para repartir pocas respuestas en más campeones.
DUO_SYNERGY_TIER: Final = 1

#: Una dupla: dos (campeón, rol).
Duo = tuple[tuple[int, LaneRole], tuple[int, LaneRole]]


@dataclass(frozen=True, slots=True)
class Combination:
    """Una pregunta que existe conceptualmente aunque no esté en la base (`21-sampler.md` §2.2).

    Llega ya en forma canónica: `(A,B)` y `(B,A)` son la misma pregunta y el CHECK
    `questions_canonical_order` exige `champion_a < champion_b` (y, en las duplas, `c < d` y
    `a < c`). Los roles de las duplas viajan con su campeón.
    """

    type: QuestionType
    champion_a: int
    champion_b: int | None = None
    dimension_id: int | None = None
    role: LaneRole | None = None
    champion_c: int | None = None
    champion_d: int | None = None
    duo_ctx: DuoContext | None = None
    role_a: LaneRole | None = None
    role_b: LaneRole | None = None
    role_c: LaneRole | None = None
    role_d: LaneRole | None = None


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
class DuoPool:
    """Los candidatos de un contexto de dupla: quién puede ocupar cada uno de sus dos lugares."""

    context: DuoContext
    first: tuple[int, ...]
    second: tuple[int, ...]

    @classmethod
    def of(cls, context: DuoContext, champions: Sequence[Champion]) -> DuoPool:
        first_role, second_role = DUO_ROLES[context]
        return cls(
            context=context,
            first=tuple(c.champion_id for c in champions if first_role.value in _role_names(c)),
            second=tuple(
                c.champion_id for c in champions if second_role.value in _role_names(c)
            ),
        )

    @property
    def roles(self) -> tuple[LaneRole, LaneRole]:
        return DUO_ROLES[self.context]

    def duo_count(self) -> int:
        """Duplas posibles: un campeón de cada lugar, distintos entre sí."""
        both = set(self.first) & set(self.second)
        return len(self.first) * len(self.second) - len(both)

    def pair_count(self) -> int:
        """Pares de duplas con los cuatro campeones distintos, sin enumerarlos.

        Inclusión-exclusión sobre los campeones compartidos: a los `C(D, 2)` pares se les restan
        los que comparten un campeón, `Σ C(d_c, 2)`, y se les suman los que comparten los dos
        —la misma pareja con los roles invertidos—, que esa suma restó dos veces.
        """
        first, second = set(self.first), set(self.second)
        both = first & second
        shared = 0
        for champion in first | second:
            duos = 0
            if champion in first:
                duos += len(second) - (1 if champion in second else 0)
            if champion in second:
                duos += len(first) - (1 if champion in first else 0)
            shared += math.comb(duos, 2)
        return math.comb(self.duo_count(), 2) - shared + math.comb(len(both), 2)

    def draw_duo(self, rng: random.Random) -> Duo:
        while True:
            x, y = rng.choice(self.first), rng.choice(self.second)
            if x != y:
                first_role, second_role = self.roles
                return (x, first_role), (y, second_role)

    def admits(self, duo: Duo) -> bool:
        """Si cada campeón sigue teniendo el rol con que se lo preguntó, en este contexto."""
        lookup = {self.roles[0]: set(self.first), self.roles[1]: set(self.second)}
        return all(champion in lookup.get(role, set()) for champion, role in duo)


@dataclass(frozen=True, slots=True)
class Space:
    """El espacio de combinaciones habilitado (`docs/21-sampler.md` §2.3).

    Se carga una vez por lote: el catálogo son unas decenas de filas y sortear en memoria evita
    una consulta por intento.
    """

    champions: Sequence[Champion]
    dimensions: Sequence[Dimension]
    lanes: Mapping[LaneRole, Sequence[Champion]]
    traits: Sequence[Trait] = ()
    #: El 2v2 usa los campeones habilitados (20 §4.2).
    bot_lane: DuoPool | None = None
    #: El tipo 4 usa sólo los del tier 1 (20 §5), por contexto.
    synergy: Mapping[DuoContext, DuoPool] = field(default_factory=dict)
    champion_ids: frozenset[int] = field(default_factory=frozenset)
    dimension_ids: frozenset[int] = field(default_factory=frozenset)
    lane_ids: Mapping[LaneRole, frozenset[int]] = field(default_factory=dict)

    @classmethod
    def of(
        cls,
        champions: Sequence[Champion],
        dimensions: Sequence[Dimension],
        traits: Sequence[Trait] = (),
    ) -> Space:
        lanes = lane_pools(champions)
        bot_lane = DuoPool.of(DuoContext.BOT, champions)
        tier_one = [c for c in champions if c.pool_tier == DUO_SYNERGY_TIER]
        synergy = {context: DuoPool.of(context, tier_one) for context in DUO_ROLES}
        return cls(
            champions=champions,
            dimensions=dimensions,
            lanes=lanes,
            traits=traits,
            bot_lane=bot_lane if bot_lane.pair_count() > 0 else None,
            synergy={c: pool for c, pool in synergy.items() if pool.pair_count() > 0},
            champion_ids=frozenset(c.champion_id for c in champions),
            dimension_ids=frozenset(d.dimension_id for d in dimensions),
            lane_ids={
                role: frozenset(c.champion_id for c in members) for role, members in lanes.items()
            },
        )

    def roles_without_pair(self) -> list[LaneRole]:
        """Los roles del 1v1 que este pool no puede servir, para el registro de §8."""
        return [role for role in LANE_1V1_ROLES if role not in self.lanes]

    def available_variants(self) -> frozenset[Variant]:
        """Las variantes que tienen al menos una combinación posible."""
        available: set[Variant] = set()
        if len(self.champions) >= RANKING_SIZE and self.dimensions:
            available.add(Variant.PAIRWISE)
        if self.champions:
            available.add(Variant.PEAK)
        if self.lanes:
            available.add(Variant.LANE_1V1)
        if self.bot_lane is not None:
            available.add(Variant.LANE_2V2)
        if self.synergy:
            available.add(Variant.DUO_SYNERGY)
        if self.champions and self.traits:
            available.add(Variant.TRAITS)
        return frozenset(available)

    def available_types(self) -> frozenset[QuestionType]:
        return frozenset(v.question_type for v in self.available_variants())

    def admits(self, question: Question) -> bool:
        """Si el pool actual todavía puede servir esta pregunta ya materializada.

        Una pregunta se generó con el pool de ese momento. Si después un campeón bajó de tier,
        una dimensión se desactivó o un campeón dejó de tener el rol (ADR-019), la fila sigue en
        la base —y sus respuestas siguen valiendo— pero no se vuelve a mostrar (21 §8).
        """
        if question.type not in SERVED_TYPES:
            return False
        variant = variant_of(question)
        if variant in (Variant.LANE_2V2, Variant.DUO_SYNERGY):
            return self._admits_duos(question, variant)
        members = [c for c in (question.champion_a, question.champion_b) if c is not None]
        if not all(c in self.champion_ids for c in members):
            return False
        if question.dimension_id is not None and question.dimension_id not in self.dimension_ids:
            return False
        if variant is Variant.PAIRWISE and question.dimension_id is None:
            return False
        if variant is Variant.TRAITS:
            return bool(self.traits)
        if variant is Variant.LANE_1V1:
            if question.role is None:
                return False
            lane = self.lane_ids.get(LaneRole(str(question.role)))
            return lane is not None and all(c in lane for c in members)
        return True

    def _admits_duos(self, question: Question, variant: Variant) -> bool:
        if question.duo_ctx is None:
            return False
        context = DuoContext(str(question.duo_ctx))
        pool = self.bot_lane if variant is Variant.LANE_2V2 else self.synergy.get(context)
        if pool is None or pool.context is not context:
            return False
        duos = duos_of(question)
        return duos is not None and all(pool.admits(duo) for duo in duos)


def duos_of(question: Question | Combination) -> tuple[Duo, Duo] | None:
    """Las dos duplas de una pregunta, o `None` si le falta algún campeón o rol."""
    a, b, c, d = question.champion_a, question.champion_b, question.champion_c, question.champion_d
    roles = (question.role_a, question.role_b, question.role_c, question.role_d)
    if b is None or c is None or d is None or any(r is None for r in roles):
        return None
    ra, rb, rc, rd = (LaneRole(str(r)) for r in roles)
    return ((a, ra), (b, rb)), ((c, rc), (d, rd))


def _canonical(a: Champion, b: Champion) -> tuple[int, int]:
    low, high = sorted((a.champion_id, b.champion_id))
    return low, high


def canonical_duos(
    question_type: QuestionType, context: DuoContext, one: Duo, two: Duo
) -> Combination:
    """Dos duplas en forma canónica: cada una ordenada por id, y la del menor id primero.

    Los roles se reordenan junto con su campeón: el orden canónico no borra quién juega qué
    (ADR-026).
    """
    (a, ra), (b, rb) = sorted(one)
    (c, rc), (d, rd) = sorted(two)
    if c < a:
        (a, ra, b, rb), (c, rc, d, rd) = (c, rc, d, rd), (a, ra, b, rb)
    return Combination(
        question_type,
        a,
        champion_b=b,
        champion_c=c,
        champion_d=d,
        duo_ctx=context,
        role_a=ra,
        role_b=rb,
        role_c=rc,
        role_d=rd,
    )


def _draw_duo_pair(
    question_type: QuestionType, pool: DuoPool, rng: random.Random
) -> Combination:
    """Dos duplas disjuntas, uniformes: se sortean por separado y se rechaza si comparten un
    campeón, lo que da la uniforme sobre los pares disjuntos sin enumerarlos (21 §4.4)."""
    while True:
        one, two = pool.draw_duo(rng), pool.draw_duo(rng)
        if not {c for c, _ in one} & {c for c, _ in two}:
            return canonical_duos(question_type, pool.context, one, two)


def draw_combination(variant: Variant, space: Space, rng: random.Random) -> Combination:
    """Sortea una combinación uniforme de la variante, sin enumerar el espacio (§4.4)."""
    match variant:
        case Variant.PAIRWISE:
            dimension = rng.choice(space.dimensions)
            a, b = rng.sample(list(space.champions), 2)
            low, high = _canonical(a, b)
            return Combination(
                QuestionType.PAIRWISE_DIMENSION,
                low,
                champion_b=high,
                dimension_id=dimension.dimension_id,
            )
        case Variant.PEAK:
            return Combination(QuestionType.PEAK_TIMING, rng.choice(space.champions).champion_id)
        case Variant.LANE_1V1:
            # Primero el rol y después el par, que tiene que compartir el rol que se muestra. El
            # rol se pesa por su cantidad de pares (errata de §4.4 del 16/09): con un rol
            # uniforme, un par del rol más chico saldría más seguido que uno del más grande.
            roles = list(space.lanes)
            weights = [math.comb(len(space.lanes[role]), 2) for role in roles]
            role = rng.choices(roles, weights=weights)[0]
            a, b = rng.sample(list(space.lanes[role]), 2)
            low, high = _canonical(a, b)
            return Combination(QuestionType.LANE_MATCHUP, low, champion_b=high, role=role)
        case Variant.LANE_2V2:
            assert space.bot_lane is not None
            return _draw_duo_pair(QuestionType.LANE_MATCHUP, space.bot_lane, rng)
        case Variant.DUO_SYNERGY:
            # El contexto se pesa por sus pares de duplas, por la misma razón que el rol del 1v1
            # (20 §5, nota del 29/10).
            contexts = list(space.synergy)
            weights = [space.synergy[c].pair_count() for c in contexts]
            context = rng.choices(contexts, weights=weights)[0]
            return _draw_duo_pair(QuestionType.DUO_SYNERGY, space.synergy[context], rng)
        case Variant.TRAITS:
            return Combination(
                QuestionType.TRAIT_MULTISELECT, rng.choice(space.champions).champion_id
            )


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


async def active_traits(session: AsyncSession) -> list[Trait]:
    return list(
        (
            await session.execute(
                sa.select(Trait)
                .where(Trait.is_active)
                .order_by(Trait.display_order, Trait.trait_id)
            )
        ).scalars()
    )


async def load_space(session: AsyncSession) -> Space:
    return Space.of(
        await enabled_champions(session),
        await active_dimensions(session),
        await active_traits(session),
    )


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


#: Las columnas de `questions_identity`, en el orden del índice.
_IDENTITY_FIELDS: Final = (
    "type",
    "champion_a",
    "champion_b",
    "champion_c",
    "champion_d",
    "dimension_id",
    "role",
    "duo_ctx",
    "role_a",
    "role_b",
    "role_c",
    "role_d",
)


def identity(combination: Combination, patch_id: int) -> list[sa.ColumnElement[bool]]:
    """Las columnas de `questions_identity`, con `IS NULL` en las que el tipo no usa.

    Un `= NULL` nunca es verdadero: sin la comparación explícita, un pico de Kayle podría
    confundirse con cualquier otra pregunta que empiece por Kayle.
    """
    columns: list[tuple[InstrumentedAttribute[Any], object]] = [(Question.patch_id, patch_id)]
    columns += [
        (getattr(Question, name), getattr(combination, name)) for name in _IDENTITY_FIELDS
    ]
    return [column.is_(None) if value is None else column == value for column, value in columns]


def _values(combination: Combination, patch_id: int) -> dict[str, Any]:
    """Todas las columnas de identidad, también las nulas: un `INSERT` de varias filas exige que
    todas tengan las mismas claves."""
    return {"patch_id": patch_id} | {
        name: getattr(combination, name) for name in _IDENTITY_FIELDS
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


def _es(spanish: str | None, english: str, lang: Lang) -> str:
    """El texto en español si se pidió y existe; si no, el inglés (ADR-028)."""
    return spanish if lang == "es" and spanish else english


def render(
    question: Question,
    champions: Mapping[int, Champion],
    dimensions: Mapping[int, Dimension],
    ranking: Ranking | None = None,
    traits: Sequence[Trait] = (),
    lang: Lang = DEFAULT_LANG,
) -> QuestionOut:
    """El enunciado ya compuesto, como exige `docs/12-api.md` §1.1. El cliente no ve plantillas.

    Una pregunta de tipo 1 se sirve como el ancla de `ranking` (ADR-022), y sin él no se puede
    renderizar. Una de tipo 5 necesita los atributos activos.
    """
    match variant_of(question):
        case Variant.PAIRWISE:
            assert question.dimension_id is not None and ranking is not None
            return render_ranking(ranking, dimensions[question.dimension_id], champions, lang)
        case Variant.PEAK:
            return render_peak(question, champions, lang)
        case Variant.LANE_1V1:
            return render_lane(question, champions, lang)
        case Variant.LANE_2V2:
            return render_bot_lane(question, champions, lang)
        case Variant.DUO_SYNERGY:
            return render_synergy(question, champions, lang)
        case Variant.TRAITS:
            return render_traits(question, champions, traits, lang)


def render_ranking(
    ranking: Ranking,
    dimension: Dimension,
    champions: Mapping[int, Champion],
    lang: Lang = DEFAULT_LANG,
) -> PairwiseDimensionQuestion:
    """Tipo 1, el ranking de cinco (ADR-022). Los campeones van en el orden guardado, que es
    aleatorio. El enunciado sale de `dimensions`, no del código: agregar una dimensión es insertar
    una fila (RF-603, CA-601)."""
    texts = question_texts.texts(lang)
    return PairwiseDimensionQuestion(
        question_id=ranking.anchor_question_id,
        ranking_id=ranking.ranking_id,
        prompt=_es(dimension.prompt_es, dimension.prompt_en, lang),
        instruction=texts.ranking_instruction,
        help=Help(
            label=_es(dimension.label_es, dimension.label_en, lang),
            text=_es(dimension.description_es, dimension.description_en, lang),
        ),
        champions=[champion_ref(champions[c]) for c in ranking.champions],
        unknown_label=texts.unknown_label,
    )


def render_peak(
    question: Question, champions: Mapping[int, Champion], lang: Lang = DEFAULT_LANG
) -> PeakTimingQuestion:
    """Tipo 2. Los textos y la escala son constantes del backend (ADR-018)."""
    texts = question_texts.texts(lang)
    champion = champions[question.champion_a]
    return PeakTimingQuestion(
        question_id=question.question_id,
        prompt=texts.peak_prompt.format(name=champion.display_name),
        help=Help(label=texts.peak_help_label, text=texts.peak_help_text),
        subject=Subject(champions=[champion_ref(champion)]),
        slider=Slider(
            min=question_texts.PEAK_MIN,
            max=question_texts.PEAK_MAX,
            step=question_texts.PEAK_STEP,
            default=question_texts.PEAK_DEFAULT,
            unit=texts.peak_unit,
            marks=[SliderMark(at=at, label=label) for at, label in texts.peak_marks],
        ),
    )


def render_lane(
    question: Question, champions: Mapping[int, Champion], lang: Lang = DEFAULT_LANG
) -> LaneMatchupQuestion:
    """Tipo 3, variante 1v1."""
    assert question.champion_b is not None and question.role is not None
    texts = question_texts.texts(lang)
    a = champions[question.champion_a]
    b = champions[question.champion_b]
    role = LaneRole(str(question.role))
    return LaneMatchupQuestion(
        question_id=question.question_id,
        prompt=texts.lane_prompt,
        help=Help(label=texts.lane_help_label, text=texts.lane_help_text),
        context=LaneContext(role=role, label=role_label(role)),
        sides=[
            Side(key="a", champions=[champion_ref(a)]),
            Side(key="b", champions=[champion_ref(b)]),
        ],
        options=[
            Option(key=key, label=template.format(a=a.display_name, b=b.display_name))
            for key, template in texts.lane_option_templates.items()
        ],
    )


def _duo_sides(
    question: Question, keys: tuple[str, str], champions: Mapping[int, Champion]
) -> list[Side]:
    """Los dos lados de una pregunta de duplas, cada uno en el orden de roles del contexto
    (ADR-026): primero el adc, el top o el mid."""
    duos = duos_of(question)
    assert duos is not None and question.duo_ctx is not None
    first_role = DUO_ROLES[DuoContext(str(question.duo_ctx))][0]
    sides: list[Side] = []
    for key, duo in zip(keys, duos, strict=True):
        ordered = sorted(duo, key=lambda member: member[1] is not first_role)
        sides.append(Side(key=key, champions=[champion_ref(champions[c]) for c, _ in ordered]))
    return sides


def render_bot_lane(
    question: Question, champions: Mapping[int, Champion], lang: Lang = DEFAULT_LANG
) -> LaneMatchupQuestion:
    """Tipo 3, variante 2v2: la dupla de arriba es `a` (`docs/12-api.md` §2.3)."""
    texts = question_texts.texts(lang)
    return LaneMatchupQuestion(
        question_id=question.question_id,
        prompt=texts.bot_prompt,
        help=Help(label=texts.bot_help_label, text=texts.bot_help_text),
        context=LaneContext(
            duo_context=DuoContext.BOT, label=texts.duo_context_labels[DuoContext.BOT]
        ),
        sides=_duo_sides(question, ("a", "b"), champions),
        options=[Option(key=key, label=label) for key, label in texts.bot_option_labels.items()],
    )


def render_synergy(
    question: Question, champions: Mapping[int, Champion], lang: Lang = DEFAULT_LANG
) -> DuoSynergyQuestion:
    """Tipo 4. Las opciones van siempre en el orden `pair_1`, `similar`, `pair_2`: el
    *straightlining* se cuenta por la clave (22 §5.2, nota del 29/10)."""
    assert question.duo_ctx is not None
    texts = question_texts.texts(lang)
    context = DuoContext(str(question.duo_ctx))
    return DuoSynergyQuestion(
        question_id=question.question_id,
        prompt=texts.duo_prompt,
        help=Help(label=texts.duo_help_label, text=texts.duo_help_text),
        context=DuoContextOut(duo_context=context, label=texts.duo_context_labels[context]),
        sides=_duo_sides(question, ("pair_1", "pair_2"), champions),
        options=[Option(key=key, label=label) for key, label in texts.duo_option_labels.items()],
    )


def render_traits(
    question: Question,
    champions: Mapping[int, Champion],
    traits: Sequence[Trait],
    lang: Lang = DEFAULT_LANG,
) -> TraitMultiselectQuestion:
    """Tipo 5. Los atributos salen de `traits`, en su `display_order` (CA-506)."""
    texts = question_texts.texts(lang)
    champion = champions[question.champion_a]
    return TraitMultiselectQuestion(
        question_id=question.question_id,
        prompt=texts.traits_prompt.format(name=champion.display_name),
        subtitle=texts.traits_subtitle,
        help=None,
        subject=Subject(champions=[champion_ref(champion)]),
        traits=[
            TraitOption(
                code=trait.code,
                label=_es(trait.label_es, trait.label_en, lang),
                help=_es(trait.description_es, trait.description_en, lang),
            )
            for trait in traits
        ],
    )
