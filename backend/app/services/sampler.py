"""El sampler: qué pregunta mostrar a continuación (`docs/21-sampler.md`).

Para cada posición del lote decide, en este orden (§6 y §10):

1. **Honeypot**, si su cadencia está vencida (`docs/22-calidad-de-datos.md` §3.6).
2. **Retest**, si el suyo está vencido y la posición quedó libre (22 §4).
3. **La variante**: las tres primeras son de tipo 1, nunca más de tres seguidas del mismo tipo, y
   el resto por la mezcla 50/20/15/5/5/5 entre las seis variantes, renormalizada sobre las que
   tienen candidatas.
4. **La pregunta dentro del tipo**: el mejor puente sin responder (tipo 1, ADR-021); si no hay,
   exploración con probabilidad `ε` o explotación por prioridad, y cada rama cae en la otra si se
   queda sin candidatas (§5, nota del 16/09).
5. **Un retest como último recurso** si ningún tipo tiene nada (§8).

Una pregunta de tipo 1 elegida así es el **par ancla** de un ranking de cinco campeones, que se
arma al final del lote (ADR-022, §5.1).

La posición es la del respondedor, no la del lote: la pregunta `k` de un lote pedido con
`answers_count = n` ocupa la posición `n + k`. Las cadencias viven en `respondents`
([ADR-020]).

**Presupuesto: 100 ms p95** (RNF-01). El sampler lee columnas denormalizadas e indexadas y nunca
agrega sobre `responses`; lo que necesita de cada tipo lo trae una vez por lote.
"""

from __future__ import annotations

import logging
import random
import uuid
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Question, QuestionType, Ranking, Respondent, Response
from app.schemas.questions import QuestionOut
from app.services import app_settings, honeypots, questions, rankings, retests, submissions
from app.services.question_texts import DEFAULT_LANG, Lang
from app.services.questions import SERVED_TYPES, Space, Variant

logger = logging.getLogger(__name__)

#: Cuántas preguntas de tipo 1 abren la historia de un respondedor: son las más fáciles de
#: entender sin instrucciones (`docs/20-tipos-de-pregunta.md` §7, CA-102).
WARMUP_PAIRWISE: Final = 3

#: La mezcla de `docs/20-tipos-de-pregunta.md` §7, por **variante**: el 1v1 (15 %) y el 2v2
#: (5 %) comparten `QuestionType.LANE_MATCHUP` y no su peso. `random.choices` renormaliza sola
#: sobre las variantes que tienen candidatas.
TYPE_WEIGHTS: dict[Variant, int] = {
    Variant.PAIRWISE: 50,
    Variant.PEAK: 20,
    Variant.LANE_1V1: 15,
    Variant.LANE_2V2: 5,
    Variant.DUO_SYNERGY: 5,
    Variant.TRAITS: 5,
}

#: La regla de variedad: nunca más de tres seguidas del mismo tipo (20 §7).
VARIETY_MAX_RUN: Final = 3

DEFAULT_WEIGHTS: Final = {"escasez": 0.35, "informacion": 0.25, "cobertura": 0.20, "puente": 1.00}

_rng = random.Random()


@dataclass(frozen=True, slots=True)
class SamplerConfig:
    """Los parámetros de §9 y los de cadencia de 22 §8, leídos de `app_settings` (RF-606)."""

    epsilon: float
    weights: Mapping[str, float]
    cold_threshold: int
    candidate_limit: int
    max_retries: int
    honeypot_every: tuple[int, int]
    retest_every: int
    retest_min_distance: int

    @classmethod
    async def load(cls, session: AsyncSession) -> SamplerConfig:
        get = app_settings.get
        weights = await get(session, "sampler.weights", DEFAULT_WEIGHTS)
        low, high = await get(session, "quality.honeypot_every", [10, 15])
        return cls(
            epsilon=float(await get(session, "sampler.epsilon", 1.0)),
            weights={key: float(value) for key, value in weights.items()},
            cold_threshold=int(await get(session, "sampler.cold_threshold", 5)),
            candidate_limit=int(await get(session, "sampler.candidate_limit", 50)),
            max_retries=int(await get(session, "sampler.max_rejection_retries", 10)),
            honeypot_every=(int(low), int(high)),
            retest_every=int(await get(session, "quality.retest_every", 30)),
            retest_min_distance=int(await get(session, "quality.retest_min_distance", 15)),
        )


def choose_type(
    position: int,
    available: Collection[Variant],
    rng: random.Random,
    recent: Sequence[QuestionType] = (),
) -> Variant | None:
    """La variante de la posición `position` del respondedor, contando desde cero.

    `recent` son los **tipos** de las posiciones inmediatamente anteriores, del más viejo al más
    nuevo. Si los últimos tres son del mismo tipo, sus variantes salen del sorteo —el 1v1 y el
    2v2 juntos, porque son el tipo 3 (21 §6, nota del 29/10)—, salvo que sean las únicas con
    candidatas: un lote corto es peor que una cuarta seguida.

    Lee `TYPE_WEIGHTS` en cada llamada, no al importar: es lo que permite a los tests forzar una
    variante sin tocar el sorteo.
    """
    if position < WARMUP_PAIRWISE and Variant.PAIRWISE in available:
        return Variant.PAIRWISE
    candidates = [v for v in TYPE_WEIGHTS if v in available]
    tail = list(recent[-VARIETY_MAX_RUN:])
    if len(tail) == VARIETY_MAX_RUN and len(set(tail)) == 1:
        varied = [v for v in candidates if v.question_type != tail[-1]]
        if varied:
            candidates = varied
    if not candidates:
        return None
    return rng.choices(candidates, weights=[TYPE_WEIGHTS[t] for t in candidates])[0]


def priority(weights: Mapping[str, float]) -> sa.ColumnElement[Any]:
    """La función de prioridad de §3.1, como expresión SQL.

    El puente pesa 1.00 y los otros tres suman como mucho 0.80: cualquier puente le gana a
    cualquier no-puente sin un `ORDER BY` de dos niveles. Los `NULL` —«todavía no se sabe»— valen 0.
    """
    exposure = sa.cast(Question.exposure_count, sa.Float)
    entropy = sa.func.coalesce(sa.cast(Question.entropy, sa.Float), 0.0)
    coverage = sa.func.coalesce(sa.cast(Question.coverage_deficit, sa.Float), 0.0)
    bridge = sa.case((Question.bridge_priority, 1.0), else_=0.0)
    return (
        weights["escasez"] * (1.0 / (1.0 + exposure))
        + weights["informacion"] * entropy
        + weights["cobertura"] * coverage
        + weights["puente"] * bridge
    )


def open_windows(respondent: Respondent, config: SamplerConfig, rng: random.Random) -> None:
    """Abre las ventanas de cadencia que todavía no se abrieron (ADR-020).

    Un respondedor nuevo recibe la primera honeypot entre las posiciones 9 y 14, y el primer
    retest en la 29. Uno que ya existía antes de la migración empieza a contar desde donde está.
    """
    low, high = config.honeypot_every
    if respondent.next_honeypot_at is None:
        respondent.next_honeypot_at = respondent.answers_count + rng.randint(low, high) - 1
    if respondent.next_retest_at is None:
        respondent.next_retest_at = respondent.answers_count + config.retest_every - 1


async def recent_types(session: AsyncSession, respondent_id: uuid.UUID) -> list[QuestionType]:
    """Los tipos de las últimas respuestas, del más viejo al más nuevo (regla de variedad).

    Cuenta envíos, no filas: un ranking del tipo 1 son diez filas y una sola posición (ADR-022).
    """
    rows = (
        await session.execute(
            submissions.heads(sa.select(Response.type).select_from(Response))
            .where(Response.respondent_id == respondent_id)
            .order_by(Response.created_at.desc(), Response.response_id.desc())
            .limit(VARIETY_MAX_RUN)
        )
    ).scalars()
    return [QuestionType(t) for t in reversed(list(rows))]


@dataclass(slots=True)
class _Batch:
    """El estado de un lote: lo que ya se eligió y lo que se trajo de la base una sola vez."""

    session: AsyncSession
    respondent: Respondent
    patch_id: int
    space: Space
    config: SamplerConfig
    rng: random.Random
    answered: set[int]
    recent: list[QuestionType]
    #: Las preguntas que el cliente tiene en cola sin contestar (ADR-020). No se vuelven a servir.
    queued: frozenset[int] = frozenset()
    seen: set[int] = field(default_factory=set)
    #: Los pares de los rankings que el cliente tiene en cola o que ya salieron en este lote
    #: (ADR-022). Ninguno puede ser ancla: al contestar el primer ranking, ese par queda
    #: respondido y el ancla del segundo sería un 409.
    taken: set[rankings.PairKey] = field(default_factory=set)
    exhausted: set[Variant] = field(default_factory=set)
    hot: dict[Variant, list[Question]] = field(default_factory=dict)
    bridges: list[Question] | None = None
    honeypot_tried: bool = False
    retest_tried: bool = False

    def excluded(self, question_id: int) -> bool:
        return (
            question_id in self.answered or question_id in self.seen or question_id in self.queued
        )

    def free(self, question: Question) -> bool:
        """Si el par no está ya dentro de un ranking pendiente. Sólo aplica al tipo 1."""
        if question.type is not QuestionType.PAIRWISE_DIMENSION:
            return True
        assert question.champion_b is not None and question.dimension_id is not None
        return (question.champion_a, question.champion_b, question.dimension_id) not in self.taken

    def _first_available(self, candidates: Sequence[Question]) -> Question | None:
        for question in candidates:
            if (
                not self.excluded(question.question_id)
                and self.free(question)
                and self.space.admits(question)
            ):
                return question
        return None

    async def best_bridge(self) -> Question | None:
        """El puente de mayor prioridad que este respondedor no contestó (§4.2, §8)."""
        if self.bridges is None:
            self.bridges = list(
                (
                    await self.session.execute(
                        sa.select(Question)
                        .where(
                            Question.patch_id == self.patch_id,
                            Question.bridge_priority,
                            Question.type == QuestionType.PAIRWISE_DIMENSION,
                            ~Question.is_honeypot,
                        )
                        .order_by(priority(self.config.weights).desc(), Question.question_id)
                    )
                ).scalars()
            )
        return self._first_available(self.bridges)

    async def best_hot(self, variant: Variant) -> Question | None:
        """Explotación (§3, §5): las mejores `candidate_limit`, descartando en memoria."""
        if variant not in self.hot:
            enabled = sorted(self.space.champion_ids)
            members = [
                sa.or_(column.is_(None), column.in_(enabled))
                for column in (Question.champion_b, Question.champion_c, Question.champion_d)
            ]
            # Las dos variantes del tipo 3 se distinguen por el tercer campeón.
            shape: list[sa.ColumnElement[bool]] = []
            if variant is Variant.LANE_1V1:
                shape.append(Question.champion_c.is_(None))
            elif variant is Variant.LANE_2V2:
                shape.append(Question.champion_c.is_not(None))
            self.hot[variant] = list(
                (
                    await self.session.execute(
                        sa.select(Question)
                        .where(
                            Question.type == variant.question_type,
                            Question.patch_id == self.patch_id,
                            ~Question.is_honeypot,
                            Question.exposure_count >= self.config.cold_threshold,
                            Question.champion_a.in_(enabled),
                            *members,
                            *shape,
                        )
                        .order_by(priority(self.config.weights).desc(), Question.question_id)
                        .limit(self.config.candidate_limit)
                    )
                ).scalars()
            )
        return self._first_available(self.hot[variant])

    async def explore(self, variant: Variant) -> Question | None:
        """Exploración (§4.2): un sorteo uniforme con rechazo y reintento (§5).

        Se rechaza lo ya respondido, lo que el cliente tiene en cola, lo ya elegido en el lote y
        las honeypots: éstas sólo salen de su catálogo y con su cadencia (nota del 16/09 en §5).
        """
        for _ in range(self.config.max_retries):
            combination = questions.draw_combination(variant, self.space, self.rng)
            question = await questions.materialize(self.session, self.patch_id, combination)
            if (
                question.is_honeypot
                or self.excluded(question.question_id)
                or not self.free(question)
            ):
                continue
            return question
        return None

    async def in_type(self, variant: Variant) -> Question | None:
        if variant is Variant.PAIRWISE:
            bridge = await self.best_bridge()
            if bridge is not None:
                return bridge
        if self.rng.random() < self.config.epsilon:
            return await self.explore(variant) or await self.best_hot(variant)
        return await self.best_hot(variant) or await self.explore(variant)

    def _servable_again(self, question: Question | None) -> bool:
        return (
            question is not None
            and question.patch_id == self.patch_id
            and self.space.admits(question)
            and question.question_id not in self.seen
        )

    async def honeypot(self) -> Question | None:
        """La honeypot que toca: la pendiente si el cliente la perdió, o una nueva (22 §3.6).

        Mientras haya una pendiente no se elige otra. Si el cliente la tiene en cola, este lote no
        trae ninguna: una segunda saldría a dos posiciones de la primera (ADR-020).
        """
        self.honeypot_tried = True
        respondent = self.respondent
        if respondent.pending_honeypot is not None:
            if respondent.pending_honeypot in self.queued:
                return None
            pending = await self.session.get(Question, respondent.pending_honeypot)
            if (
                pending is not None
                and pending.is_honeypot
                and pending.question_id not in self.answered
                and self._servable_again(pending)
            ):
                return pending
            respondent.pending_honeypot = None

        catalog = await honeypots.catalog(self.session, self.patch_id)
        excluded = self.answered | self.seen | self.queued
        chosen = honeypots.pick_unseen(
            [q for q in catalog if self.free(q)], self.space, excluded, self.rng
        )
        if chosen is not None:
            respondent.pending_honeypot = chosen.question_id
        return chosen

    async def retest(self, position: int) -> Question | None:
        """El retest que toca: el pendiente si el cliente lo perdió, o uno nuevo (22 §4)."""
        self.retest_tried = True
        respondent = self.respondent
        if respondent.pending_retest_of is not None:
            original = await self.session.get(Response, respondent.pending_retest_of)
            question = (
                await self.session.get(Question, original.question_id)
                if original is not None
                else None
            )
            if question is not None and question.question_id in self.queued:
                return None
            if question is not None and self._servable_again(question):
                return question
            respondent.pending_retest_of = None

        picked = await retests.pick_eligible(
            self.session,
            respondent,
            self.patch_id,
            self.space,
            position,
            self.config.retest_min_distance,
            SERVED_TYPES,
            self.rng,
        )
        if picked is None:
            return None
        original_response, question = picked
        if question.question_id in self.seen or question.question_id in self.queued:
            return None
        respondent.pending_retest_of = original_response.response_id
        return question

    async def next(self, position: int) -> Question | None:
        respondent = self.respondent
        due_honeypot = respondent.next_honeypot_at is not None and (
            position >= respondent.next_honeypot_at
        )
        if due_honeypot and not self.honeypot_tried:
            question = await self.honeypot()
            if question is not None:
                return question

        due_retest = respondent.next_retest_at is not None and (
            position >= respondent.next_retest_at
        )
        if due_retest and not self.retest_tried:
            question = await self.retest(position)
            if question is not None:
                return question

        while True:
            variant = choose_type(
                position, self.space.available_variants() - self.exhausted, self.rng, self.recent
            )
            if variant is None:
                break
            question = await self.in_type(variant)
            if question is not None:
                return question
            self.exhausted.add(variant)

        # §8: el respondedor agotó todo lo disponible.
        if not self.retest_tried:
            return await self.retest(position)
        return None


async def next_batch(
    session: AsyncSession,
    respondent: Respondent,
    count: int,
    rng: random.Random | None = None,
    queued: Collection[int] = (),
    lang: Lang = DEFAULT_LANG,
) -> list[QuestionOut]:
    """Elige hasta `count` preguntas distintas y las devuelve ya renderizadas.

    `queued` son las preguntas que el cliente tiene en cola sin contestar: ninguna se vuelve a
    servir, y la primera pregunta del lote ocupa la posición `answers_count + len(queued)`
    (ADR-020). `lang` es el idioma de los textos (ADR-028).

    Si todos los tipos se agotan, el lote sale más corto y, si queda vacío, la interfaz muestra el
    estado de cola vacía. Hace commit: la exploración materializa filas y las cadencias se abren
    o se marcan en la fila del respondedor.
    """
    rng = rng or _rng
    patch = await questions.current_patch(session)
    if patch is None:
        return []
    space = await questions.load_space(session)
    if not space.available_variants():
        return []
    missing = space.roles_without_pair()
    if missing:
        # 21 §8: un rol sin pareja no es un error, pero tiene que quedar registrado.
        logger.info(
            "roles del 1v1 sin dos campeones en el pool habilitado, se saltean: %s",
            ", ".join(role.value for role in missing),
        )

    config = await SamplerConfig.load(session)
    open_windows(respondent, config, rng)
    in_queue = frozenset(queued)
    batch = _Batch(
        session=session,
        respondent=respondent,
        patch_id=patch.patch_id,
        space=space,
        config=config,
        rng=rng,
        answered=await questions.answered_question_ids(session, respondent.respondent_id),
        recent=await recent_types(session, respondent.respondent_id),
        queued=in_queue,
    )

    batch.taken = await rankings.pending_pairs(session, respondent.respondent_id, in_queue)

    chosen: list[Question] = []
    # El tipo 1 se sirve como un ranking de cinco alrededor del par elegido (ADR-022, 21 §5.1).
    # Se arma apenas se elige el ancla, para que sus pares no puedan ser el ancla de otro.
    served: dict[int, Ranking] = {}
    honeypot_pairs: set[rankings.PairKey] | None = None
    start = respondent.answers_count + len(in_queue)
    for index in range(count):
        question = await batch.next(start + index)
        if question is None:
            break
        batch.seen.add(question.question_id)
        batch.recent.append(question.type)
        chosen.append(question)
        if question.type is QuestionType.PAIRWISE_DIMENSION:
            if honeypot_pairs is None:
                honeypot_pairs = await rankings.honeypot_pairs(session, patch.patch_id)
            ranking = rankings.build(
                respondent.respondent_id, question, space, honeypot_pairs, rng, config.max_retries
            )
            session.add(ranking)
            served[question.question_id] = ranking
            batch.taken |= rankings.keys_of(ranking)
    await session.commit()

    champions = {c.champion_id: c for c in space.champions}
    dimensions = {d.dimension_id: d for d in space.dimensions}
    return [
        questions.render(q, champions, dimensions, served.get(q.question_id), space.traits, lang)
        for q in chosen
    ]
