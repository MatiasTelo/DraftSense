"""La seed de respuestas sintéticas: para probar el consenso y la agregación sin piloto.

**Sólo para una base local.** Escribe miles de respondedores y respuestas que no son de nadie;
`guard` se niega a correr si `DS_DATABASE_URL` no apunta a `localhost`, `127.0.0.1` o `::1`, para
que nunca llegue a staging ni al servidor del laboratorio. Decisión del alumno del 29/10/2026.

Las respuestas salen de una **verdad oculta** conocida, fijada por la semilla:

- un score por (campeón, dimensión), del que salen los rankings del tipo 1 (Plackett-Luce);
- un minuto de pico por campeón (tipo 2);
- una fuerza por (campeón, rol) del 1v1 y los umbrales del modelo ordinal (tipo 3);
- un efecto de campeón y una interacción por dupla, por contexto (2v2 y tipo 4);
- una probabilidad por (campeón, atributo) (tipo 5).

Con eso, `aggregation.compare_truth` mide si el pipeline recupera lo que se sembró. Los
respondedores son de tres perfiles —buenos, ruidosos y al azar, 70/20/10 por defecto— que también
contestan honeypots y retests: el trust se **calcula** con el módulo de calidad real
(`degenerate.detect` y `trust.rebuild`), no se asigna.

Los parámetros de la verdad —escalas, umbrales, ruido de cada perfil— son de la seed y no del
sistema: están acá, se registran en el JSON de verdad y no tocan `app_settings`.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import random
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import (
    DuoContext,
    LaneRole,
    Question,
    QuestionType,
    Ranking,
    Respondent,
    Response,
)
from app.models.collection import VALID_RANKS
from app.services import (
    connectivity,
    degenerate,
    question_stats,
    questions,
    rankings,
    sessions,
    trust,
)
from app.services.questions import Combination, Variant

LOCAL_HOSTS: Final = frozenset({"localhost", "127.0.0.1", "::1"})

#: Los cinco niveles del tipo 3, de «gana b por mucho» a «gana a por mucho».
LANE_SCALE: Final = ("b_strong", "b_slight", "even", "a_slight", "a_strong")
#: Los tres del tipo 4, en el mismo sentido.
SYNERGY_SCALE: Final = ("pair_2", "similar", "pair_1")
HOURS: Final = ("<5", "5-15", "15-30", "30+")


class UnsafeDatabaseError(Exception):
    """La base no es local: la seed no corre."""


def guard() -> str:
    """El host de la base, o `UnsafeDatabaseError` si no es local."""
    host = make_url(get_settings().database_url).host or ""
    if host not in LOCAL_HOSTS:
        raise UnsafeDatabaseError(
            f"la seed sintética sólo corre contra una base local; DS_DATABASE_URL apunta a {host!r}"
        )
    return host


@dataclass(frozen=True, slots=True)
class Profile:
    """Cómo contesta un perfil de respondedor."""

    name: str
    #: Cuánto de la verdad usa: 1 la sigue, 0 contesta al azar.
    signal: float
    #: Desvío del minuto de pico, en minutos.
    peak_noise: float
    honeypot_pass: float
    #: Probabilidad de repetir la misma respuesta en un retest; si no, contesta de nuevo.
    retest_repeat: float
    #: Rango del tiempo de respuesta, en ms. El perfil al azar contesta apurado.
    response_ms: tuple[int, int]
    #: Probabilidad de *Not sure* en un ranking del tipo 1.
    unknown: float


PROFILES: Final = {
    "good": Profile("good", 1.0, 2.5, 0.97, 0.85, (2500, 9000), 0.03),
    "noisy": Profile("noisy", 0.4, 6.0, 0.85, 0.6, (1500, 6000), 0.05),
    "random": Profile("random", 0.0, 0.0, 0.5, 0.0, (250, 900), 0.0),
}


@dataclass(frozen=True, slots=True)
class SeedPlan:
    """Cuántas respuestas se siembran (decisión del 29/10: todo lo chico entero, el tipo 1 y las
    duplas por muestra). Los valores por defecto apuntan a que cada magnitud por campeón llegue a
    `solid` con los pesos reales —trust por decaimiento—, no sólo a 20 respuestas."""

    respondents: int = 400
    mix: tuple[float, float, float] = (0.70, 0.20, 0.10)
    days: int = 42
    #: Tipo 1: grupos de cinco por dimensión, cada uno ordenado por `group_answers` personas
    #: distintas —así sus diez pares pasan el umbral de consenso—, más rankings al azar que
    #: conectan los grupos y suman soporte.
    groups_per_dimension: int = 12
    group_answers: int = 22
    random_rankings_per_dimension: int = 1200
    peak_answers: int = 35
    trait_answers: int = 80
    lane_answers: int = 25
    duo_questions_per_context: int = 150
    duo_answers: int = 22
    honeypot_every: int = 12
    retests_per_respondent: int = 3


@dataclass(slots=True)
class Truth:
    dimensions: dict[str, dict[int, float]] = field(default_factory=dict)
    peak: dict[int, int] = field(default_factory=dict)
    lane: dict[str, dict[int, float]] = field(default_factory=dict)
    lane_thresholds: tuple[float, float] = (0.6, 1.8)
    bot_lane: dict[str, dict[str, float]] = field(default_factory=dict)
    synergy: dict[str, dict[str, dict[str, float]]] = field(default_factory=dict)
    synergy_threshold: float = 0.5
    traits: dict[int, dict[str, float]] = field(default_factory=dict)

    def as_json(self, seed: int, plan: SeedPlan, profiles: dict[str, int]) -> dict[str, Any]:
        return {
            "seed": seed,
            "plan": _plan_dict(plan),
            "profiles": profiles,
            "dimensions": {d: _keys(v) for d, v in self.dimensions.items()},
            "peak": _keys(self.peak),
            "lane": {r: _keys(v) for r, v in self.lane.items()},
            "lane_thresholds": list(self.lane_thresholds),
            "bot_lane": self.bot_lane,
            "synergy": self.synergy,
            "synergy_threshold": self.synergy_threshold,
            "traits": {str(c): v for c, v in self.traits.items()},
        }


def _plan_dict(plan: SeedPlan) -> dict[str, Any]:
    return {name: getattr(plan, name) for name in plan.__dataclass_fields__}


def _keys(values: dict[int, Any]) -> dict[str, Any]:
    return {str(k): v for k, v in values.items()}


def duo_label(duo: Sequence[tuple[int, LaneRole]]) -> str:
    """`12:adc|99:support`, ordenado por id: la clave de una dupla en el JSON de verdad."""
    return "|".join(f"{c}:{r.value}" for c, r in sorted(duo, key=lambda m: m[0]))


@dataclass(slots=True)
class SeedResult:
    respondents: int
    responses: int
    rankings: int
    profiles: dict[str, int]
    truth_path: Path


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def ordinal_level(delta: float, cuts: Sequence[float], rng: random.Random) -> int:
    """Un nivel de 0 a K-1 con `P(Y >= k) = sigmoid(delta - t_k)` (`docs/25-agregacion.md` §5.3)."""
    u = rng.random()
    level = 0
    for cut in cuts:
        if u < _sigmoid(delta - cut):
            level += 1
    return level


def plackett_luce(
    champions: Sequence[int], strength: dict[int, float], signal: float, rng: random.Random
) -> list[int]:
    """Un orden de más a menos: se elige el primero con probabilidad ∝ exp(θ), y así."""
    remaining = list(champions)
    order: list[int] = []
    while remaining:
        weights = [math.exp(signal * strength[c]) for c in remaining]
        pick = rng.choices(remaining, weights=weights)[0]
        order.append(pick)
        remaining.remove(pick)
    return order


class _Writer:
    """Acumula las filas de `responses` y de `rankings` para insertarlas de a miles."""

    def __init__(self, patch_id: int, rng: random.Random, until: dt.datetime, days: int) -> None:
        self.patch_id = patch_id
        self.rng = rng
        self.until = until
        self.days = days
        self.rows: list[dict[str, Any]] = []
        self.answered: dict[uuid.UUID, set[int]] = {}
        self.submissions: dict[uuid.UUID, int] = {}

    def moment(self) -> dt.datetime:
        return self.until - dt.timedelta(seconds=self.rng.uniform(0, self.days * 86_400))

    def add(
        self,
        respondent: uuid.UUID,
        profile: Profile,
        question: Question,
        answer: dict[str, Any],
        *,
        created: dt.datetime | None = None,
        ranking_id: int | None = None,
        is_retest_of: int | None = None,
        count: bool = True,
    ) -> bool:
        seen = self.answered.setdefault(respondent, set())
        if is_retest_of is None:
            if question.question_id in seen:
                return False
            seen.add(question.question_id)
        self.rows.append(
            {
                "respondent_id": respondent,
                "question_id": question.question_id,
                "type": question.type,
                "patch_id": self.patch_id,
                "answer": answer,
                "response_time_ms": self.rng.randint(*profile.response_ms),
                "is_retest_of": is_retest_of,
                "ranking_id": ranking_id,
                "created_at": created or self.moment(),
            }
        )
        if count:
            self.submissions[respondent] = self.submissions.get(respondent, 0) + 1
        return True


async def _flush(session: AsyncSession, rows: list[dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    for start in range(0, len(rows), 5_000):
        chunk = rows[start : start + 5_000]
        result = await session.execute(
            sa.insert(Response).returning(Response.response_id, sort_by_parameter_order=True),
            chunk,
        )
        ids += [row[0] for row in result.all()]
    await session.commit()
    return ids


def _draw_truth(
    rng: random.Random,
    space: questions.Space,
    dimensions: Sequence[tuple[int, str]],
    trait_codes: Sequence[str],
) -> Truth:
    truth = Truth()
    ids = [c.champion_id for c in space.champions]
    for _, code in dimensions:
        # Desvío 0.7: con 1, los campeones de las puntas quedaban por encima de |2| en log-odds y su
        # intervalo no llegaba a solid aun con cientos de comparaciones.
        truth.dimensions[code] = {c: rng.gauss(0, 0.7) for c in ids}
    truth.peak = {c: rng.randint(8, 32) for c in ids}
    for role, members in space.lanes.items():
        truth.lane[role.value] = {c.champion_id: rng.gauss(0, 0.8) for c in members}
    if space.bot_lane is not None:
        pool = space.bot_lane
        effects = {str(c): rng.gauss(0, 0.6) for c in {*pool.first, *pool.second}}
        interactions = {
            duo_label(((x, pool.roles[0]), (y, pool.roles[1]))): rng.gauss(0, 0.3)
            for x in pool.first
            for y in pool.second
            if x != y
        }
        truth.bot_lane = {"a": effects, "i": interactions}
    for context, pool in space.synergy.items():
        truth.synergy[context.value] = {
            "a": {str(c): rng.gauss(0, 0.6) for c in {*pool.first, *pool.second}},
            "i": {
                duo_label(((x, pool.roles[0]), (y, pool.roles[1]))): rng.gauss(0, 0.3)
                for x in pool.first
                for y in pool.second
                if x != y
            },
        }
    truth.traits = {c: {t: rng.uniform(0.05, 0.95) for t in trait_codes} for c in ids}
    return truth


def _duo_strength(model: dict[str, dict[str, float]], duo: Sequence[tuple[int, LaneRole]]) -> float:
    return sum(model["a"].get(str(c), 0.0) for c, _ in duo) + model["i"].get(duo_label(duo), 0.0)


async def seed(
    session: AsyncSession,
    seed_value: int,
    truth_out: Path,
    plan: SeedPlan | None = None,
    until: dt.datetime | None = None,
) -> SeedResult:
    """Siembra todo y deja la base lista para el consenso y para `python -m aggregation.run`."""
    guard()
    plan = plan or SeedPlan()
    rng = random.Random(seed_value)
    patch = await questions.current_patch(session)
    if patch is None:
        raise ValueError("no hay parche vigente: activalo antes de sembrar (activate-patch)")
    space = await questions.load_space(session)
    if not space.available_variants():
        raise ValueError("el pool habilitado está vacío: cargá campeones y pick rate")
    dimensions = [(d.dimension_id, d.code) for d in space.dimensions]
    trait_codes = [t.code for t in space.traits]
    truth = _draw_truth(rng, space, dimensions, trait_codes)

    # Respondedores, con sus perfiles y lo que declararon en el onboarding (al azar: sirve para
    # probar la segmentación de la semana 10, nunca pondera).
    names = list(PROFILES)
    profiles: list[Profile] = []
    respondent_ids: list[uuid.UUID] = []
    for index in range(plan.respondents):
        created_row, _ = await sessions.create(session, f"synthetic-{seed_value}-{index}")
        created_row.declared_rank = rng.choice([*VALID_RANKS, None])
        created_row.declared_main_role = rng.choice([*LaneRole, None])
        created_row.declared_hours_bucket = rng.choice([*HOURS, None])
        profile = PROFILES[rng.choices(names, weights=plan.mix)[0]]
        profiles.append(profile)
        respondent_ids.append(created_row.respondent_id)
    await session.commit()
    profile_of = dict(zip(respondent_ids, profiles, strict=True))

    moment = until or dt.datetime.now(dt.UTC)
    writer = _Writer(patch.patch_id, rng, moment, plan.days)

    def people(k: int) -> list[uuid.UUID]:
        return rng.sample(respondent_ids, min(k, len(respondent_ids)))

    # Las honeypots del catálogo se contestan sólo como honeypots, más abajo, con el acierto del
    # perfil: un par de un ranking que sea honeypot no se guarda (ADR-022, punto 6). Contestarlas
    # desde la verdad oculta —que no sabe nada del kit— las haría fallar al azar y el job de
    # estadísticas las retiraría.
    honeypots = list(
        (
            await session.execute(
                sa.select(Question).where(
                    Question.patch_id == patch.patch_id, Question.is_honeypot
                )
            )
        ).scalars()
    )
    honeypot_ids = {q.question_id for q in honeypots}

    # --- tipo 1: rankings de cinco, guardados como diez comparaciones (ADR-022) ----------
    ranking_rows: list[tuple[uuid.UUID, int, list[int], list[int] | None, dt.datetime]] = []
    champion_ids = [c.champion_id for c in space.champions]
    for dimension_id, code in dimensions:
        strength = truth.dimensions[code]
        shuffled = champion_ids[:]
        rng.shuffle(shuffled)
        groups = [
            shuffled[i : i + 5]
            for i in range(0, 5 * plan.groups_per_dimension, 5)
            if len(shuffled[i : i + 5]) == 5
        ]
        sets: list[tuple[list[int], list[uuid.UUID]]] = [
            (group, people(plan.group_answers)) for group in groups
        ]
        sets += [
            (rng.sample(champion_ids, 5), [rng.choice(respondent_ids)])
            for _ in range(plan.random_rankings_per_dimension)
        ]
        for five, who in sets:
            for respondent in who:
                profile = profile_of[respondent]
                shown = five[:]
                rng.shuffle(shown)
                order = (
                    None
                    if rng.random() < profile.unknown
                    else plackett_luce(five, strength, profile.signal, rng)
                )
                ranking_rows.append((respondent, dimension_id, shown, order, writer.moment()))

    pairs_needed = {
        Combination(QuestionType.PAIRWISE_DIMENSION, low, champion_b=high, dimension_id=d)
        for _, d, shown, _, _ in ranking_rows
        for low, high in rankings.pairs(shown)
    }
    ordered = sorted(
        pairs_needed, key=lambda c: (c.dimension_id or 0, c.champion_a, c.champion_b or 0)
    )
    by_combination: dict[Combination, Question] = {}
    # De a mil: un INSERT de varias filas no admite más de 32 767 parámetros.
    for start in range(0, len(ordered), 1_000):
        by_combination |= await questions.materialize_many(
            session, patch.patch_id, ordered[start : start + 1_000]
        )
    await session.commit()
    ranking_models: list[Ranking] = []
    for respondent, dimension_id, shown, order, _ in ranking_rows:
        low, high = sorted(shown[:2])
        anchor = by_combination[
            Combination(
                QuestionType.PAIRWISE_DIMENSION, low, champion_b=high, dimension_id=dimension_id
            )
        ]
        ranking_models.append(
            Ranking(
                respondent_id=respondent,
                patch_id=patch.patch_id,
                dimension_id=dimension_id,
                anchor_question_id=anchor.question_id,
                champions=shown,
                submitted_order=order,
            )
        )
    session.add_all(ranking_models)
    await session.commit()
    for (respondent, dimension_id, shown, order, created), ranking in zip(
        ranking_rows, ranking_models, strict=True
    ):
        profile = profile_of[respondent]
        choices = rankings.choices_from_order(order) if order is not None else None
        counted = False
        for low, high in rankings.pairs(shown):
            question = by_combination[
                Combination(
                    QuestionType.PAIRWISE_DIMENSION, low, champion_b=high, dimension_id=dimension_id
                )
            ]
            if question.question_id in honeypot_ids:
                continue
            choice = "unknown" if choices is None else choices[(low, high)]
            added = writer.add(
                respondent,
                profile,
                question,
                {"choice": choice},
                created=created,
                ranking_id=ranking.ranking_id,
                count=not counted,
            )
            counted = counted or added

    # --- tipo 2 y tipo 5: todos los campeones del pool --------------------------------------
    for champion in space.champions:
        c = champion.champion_id
        peak_question = await questions.materialize(
            session, patch.patch_id, Combination(QuestionType.PEAK_TIMING, c)
        )
        for respondent in people(plan.peak_answers):
            profile = profile_of[respondent]
            if profile.signal == 0:
                minute = rng.randint(0, 40)
            else:
                minute = round(rng.gauss(truth.peak[c], profile.peak_noise))
            writer.add(respondent, profile, peak_question, {"minute": max(0, min(40, minute))})
        if trait_codes:
            trait_question = await questions.materialize(
                session, patch.patch_id, Combination(QuestionType.TRAIT_MULTISELECT, c)
            )
            for respondent in people(plan.trait_answers):
                profile = profile_of[respondent]
                writer.add(
                    respondent,
                    profile,
                    trait_question,
                    {"traits": _traits_answer(truth.traits[c], trait_codes, profile, rng)},
                )

    # --- tipo 3 1v1: todos los pares de cada rol --------------------------------------------
    cuts_lane = [-truth.lane_thresholds[1], -truth.lane_thresholds[0], *truth.lane_thresholds]
    for role, members in space.lanes.items():
        ids = sorted(c.champion_id for c in members)
        for low, high in itertools.combinations(ids, 2):
            question = await questions.materialize(
                session,
                patch.patch_id,
                Combination(QuestionType.LANE_MATCHUP, low, champion_b=high, role=role),
            )
            delta = truth.lane[role.value][low] - truth.lane[role.value][high]
            for respondent in people(plan.lane_answers):
                profile = profile_of[respondent]
                level = (
                    rng.randrange(5)
                    if profile.signal == 0
                    else ordinal_level(profile.signal * delta, cuts_lane, rng)
                )
                writer.add(respondent, profile, question, {"choice": LANE_SCALE[level]})

    # --- tipo 3 2v2 y tipo 4: una muestra de preguntas por contexto -------------------------
    duo_variants: list[tuple[Variant, DuoContext | None]] = []
    if space.bot_lane is not None:
        duo_variants.append((Variant.LANE_2V2, None))
    duo_variants += [(Variant.DUO_SYNERGY, context) for context in space.synergy]
    for variant, context in duo_variants:
        seen_questions: set[int] = set()
        attempts = 0
        while len(seen_questions) < plan.duo_questions_per_context and attempts < 50 * (
            plan.duo_questions_per_context
        ):
            attempts += 1
            if context is None:
                combination = questions.draw_combination(variant, space, rng)
            else:
                pool = space.synergy[context]
                combination = questions.canonical_duos(
                    QuestionType.DUO_SYNERGY, context, pool.draw_duo(rng), pool.draw_duo(rng)
                )
                distinct = {
                    combination.champion_a,
                    combination.champion_b,
                    combination.champion_c,
                    combination.champion_d,
                }
                if len(distinct) < 4:
                    continue
            question = await questions.materialize(session, patch.patch_id, combination)
            if question.question_id in seen_questions:
                continue
            seen_questions.add(question.question_id)
            duos = questions.duos_of(question)
            assert duos is not None
            top, bottom = duos
            scale: tuple[str, ...]
            if variant is Variant.LANE_2V2:
                model, cuts, scale = truth.bot_lane, cuts_lane, LANE_SCALE
            else:
                assert context is not None
                model = truth.synergy[context.value]
                cuts = [-truth.synergy_threshold, truth.synergy_threshold]
                scale = SYNERGY_SCALE
            delta = _duo_strength(model, top) - _duo_strength(model, bottom)
            for respondent in people(plan.duo_answers):
                profile = profile_of[respondent]
                level = (
                    rng.randrange(len(scale))
                    if profile.signal == 0
                    else ordinal_level(profile.signal * delta, cuts, rng)
                )
                writer.add(respondent, profile, question, {"choice": scale[level]})

    # --- honeypots: una cada `honeypot_every` respuestas, con el acierto del perfil ---------
    if honeypots:
        for respondent in respondent_ids:
            profile = profile_of[respondent]
            count = writer.submissions.get(respondent, 0) // plan.honeypot_every
            for question in rng.sample(honeypots, min(count, len(honeypots))):
                expected = question.expected_answer or {}
                passed = rng.random() < profile.honeypot_pass
                choice = expected.get("choice", "a")
                if not passed:
                    choice = "b" if choice == "a" else "a"
                writer.add(respondent, profile, question, {"choice": choice})

    ids = await _flush(session, writer.rows)
    originals = list(zip(ids, writer.rows, strict=True))

    # --- retests: repiten una respuesta propia de los tipos 2 a 5 ---------------------------
    retest_rows: list[dict[str, Any]] = []
    retest_writer = _Writer(patch.patch_id, rng, moment, plan.days)
    by_respondent: dict[uuid.UUID, list[tuple[int, dict[str, Any]]]] = {}
    for response_id, row in originals:
        if row["ranking_id"] is None and row["type"] is not QuestionType.PAIRWISE_DIMENSION:
            by_respondent.setdefault(row["respondent_id"], []).append((response_id, row))
    questions_by_id: dict[int, Question] = {}
    for respondent, candidates in by_respondent.items():
        profile = profile_of[respondent]
        for response_id, row in rng.sample(
            candidates, min(plan.retests_per_respondent, len(candidates))
        ):
            found = questions_by_id.get(row["question_id"]) or await session.get(
                Question, row["question_id"]
            )
            assert found is not None
            questions_by_id[found.question_id] = found
            answer = (
                row["answer"]
                if rng.random() < profile.retest_repeat
                else _random_answer(found, trait_codes, rng)
            )
            retest_writer.add(
                respondent,
                profile,
                found,
                answer,
                created=row["created_at"] + dt.timedelta(minutes=rng.randint(10, 600)),
                is_retest_of=response_id,
            )
    retest_rows = retest_writer.rows
    await _flush(session, retest_rows)

    # --- contadores y calidad ---------------------------------------------------------------
    totals = {
        r: writer.submissions.get(r, 0) + retest_writer.submissions.get(r, 0)
        for r in respondent_ids
    }
    for row_model in (
        await session.execute(
            sa.select(Respondent).where(Respondent.respondent_id.in_(respondent_ids))
        )
    ).scalars():
        row_model.answers_count = totals[row_model.respondent_id]
        row_model.last_seen = moment
    await session.commit()
    await degenerate.detect(session, now=moment, since_hours=24 * (plan.days + 2))
    await trust.rebuild(session, respondent_ids, await trust.TrustParams.load(session))
    await session.commit()
    await question_stats.refresh(session)
    await connectivity.check(session, rng)

    counts = {name: sum(1 for p in profiles if p.name == name) for name in names}
    truth_out.parent.mkdir(parents=True, exist_ok=True)
    truth_out.write_text(
        json.dumps(truth.as_json(seed_value, plan, counts), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return SeedResult(
        respondents=len(respondent_ids),
        responses=len(writer.rows) + len(retest_rows),
        rankings=len(ranking_models),
        profiles=counts,
        truth_path=truth_out,
    )


def _traits_answer(
    probabilities: dict[str, float], codes: Sequence[str], profile: Profile, rng: random.Random
) -> list[str]:
    """Al menos un atributo (ADR-027): si no salió ninguno, se vuelve a sortear."""
    for _ in range(50):
        chosen = [
            code
            for code in codes
            if rng.random() < 0.5 + profile.signal * (probabilities[code] - 0.5)
        ]
        if chosen:
            return chosen
    return [rng.choice(list(codes))]


def _random_answer(
    question: Question, trait_codes: Sequence[str], rng: random.Random
) -> dict[str, Any]:
    match question.type:
        case QuestionType.PEAK_TIMING:
            return {"minute": rng.randint(0, 40)}
        case QuestionType.LANE_MATCHUP:
            return {"choice": rng.choice(LANE_SCALE)}
        case QuestionType.DUO_SYNERGY:
            return {"choice": rng.choice(SYNERGY_SCALE)}
        case QuestionType.TRAIT_MULTISELECT:
            return {"traits": rng.sample(list(trait_codes), rng.randint(1, len(trait_codes)))}
        case _:
            return {"choice": rng.choice(("a", "b"))}


__all__ = [
    "PROFILES",
    "SeedPlan",
    "SeedResult",
    "UnsafeDatabaseError",
    "guard",
    "seed",
]
