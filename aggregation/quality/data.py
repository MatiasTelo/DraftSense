"""Lo que el informe necesita y la corrida no tiene (`docs/27-validacion-confiabilidad.md` §10).

El conjunto filtrado de `load.py` deja afuera, a propósito, los retests, las honeypots y a los
respondedores marcados o bajo `min_trust` (25 §1.2). El test-retest, las honeypots, el trust por
horas y la huella se miden justamente sobre eso, así que tienen consultas propias.

**Población de §1.1:** test-retest, honeypots y trust por horas usan a los respondedores **no
marcados** con alguna respuesta en la ventana, **sin filtro de trust**. Filtrar por trust antes de
medirlos los inflaría por construcción, porque el trust se calcula con ellos.

Todo se devuelve ordenado: el informe entra en CA-408 y no puede depender del orden de la base.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from aggregation.load import window
from aggregation.params import RunParams
from app.models import Dimension, Question, QuestionType, Respondent, Response
from app.services import app_settings, honeypots, retests


@dataclass(frozen=True, slots=True)
class Person:
    respondent_id: uuid.UUID
    rank: str | None
    main_role: str | None
    hours: str | None
    trust: float
    flagged: bool


@dataclass(frozen=True, slots=True)
class Honeypot:
    question_id: int
    patch: str
    dimension: str
    champion_a: int
    champion_b: int


@dataclass(frozen=True, slots=True)
class HoneypotAnswer:
    question_id: int
    respondent_id: uuid.UUID
    #: `None` si contestó `unknown`: no es intento (22 §3.5).
    passed: bool | None


@dataclass(frozen=True, slots=True)
class RetestPair:
    respondent_id: uuid.UUID
    #: `pairwise_dimension`, `peak_timing`, `lane_1v1`, `lane_2v2`, `duo_synergy` o
    #: `trait_multiselect`: el 2v2 se separa del 1v1 (27 §3).
    kind: str
    #: `None` si el par no cuenta (`unknown` en el tipo 1, 22 §4).
    consistent: bool | None


@dataclass(frozen=True, slots=True)
class Excluded:
    """Las respuestas de la ventana que no entraron, en el orden de los filtros de 25 §1.2."""

    window: int
    retest: int
    honeypot: int
    flagged: int
    trust: int


@dataclass(frozen=True, slots=True)
class Settings:
    honeypot_min_attempts: int
    fingerprint_max_identities: int
    segment_min_respondents: int
    segment_min_comparisons: int


@dataclass(slots=True)
class Extra:
    #: Todo respondedor con alguna respuesta en la ventana, marcado o no.
    people: dict[uuid.UUID, Person]
    honeypots: dict[int, Honeypot]
    honeypot_answers: list[HoneypotAnswer]
    retests: list[RetestPair]
    #: `(versión, honeypots activas)` por parche de la ventana, en orden de salida.
    active_honeypots: list[tuple[str, int]]
    excluded: Excluded
    settings: Settings
    patches: list[str] = field(default_factory=list)


def _kind(question_type: QuestionType, champion_c: int | None) -> str:
    if question_type is QuestionType.LANE_MATCHUP:
        return "lane_2v2" if champion_c is not None else "lane_1v1"
    return question_type.value


async def load_extra(session: AsyncSession, params: RunParams) -> Extra:
    patches = await window(session, params)
    patch_ids = [p.patch_id for p in patches]
    in_window = Response.patch_id.in_(patch_ids)

    active = sa.select(Response.respondent_id).where(in_window).distinct().scalar_subquery()
    people = {
        r.respondent_id: Person(
            respondent_id=r.respondent_id,
            rank=r.declared_rank,
            main_role=None if r.declared_main_role is None else str(r.declared_main_role),
            hours=r.declared_hours_bucket,
            trust=float(r.trust_score),
            flagged=r.is_flagged,
        )
        for r in (
            await session.execute(
                sa.select(Respondent)
                .where(Respondent.respondent_id.in_(active))
                .order_by(Respondent.respondent_id)
            )
        ).scalars()
    }

    # Las honeypots vigentes de la ventana, que es la misma regla con la que la corrida las deja
    # afuera (27 §4.1): una ya retirada es una pregunta común.
    version = {p.patch_id: p.version for p in patches}
    rows = await session.execute(
        sa.select(Question, Dimension.code)
        .join(Dimension, Dimension.dimension_id == Question.dimension_id)
        .where(Question.patch_id.in_(patch_ids), Question.is_honeypot)
        .order_by(Question.question_id)
    )
    catalog: dict[int, Honeypot] = {}
    expected: dict[int, dict[str, object] | None] = {}
    for question, code in rows.tuples():
        assert question.champion_b is not None
        catalog[question.question_id] = Honeypot(
            question_id=question.question_id,
            patch=version[question.patch_id],
            dimension=code,
            champion_a=question.champion_a,
            champion_b=question.champion_b,
        )
        expected[question.question_id] = question.expected_answer
    active_honeypots = [
        (p.version, sum(1 for h in catalog.values() if h.patch == p.version)) for p in patches
    ]

    answers: list[HoneypotAnswer] = []
    if catalog:
        honeypot_rows = await session.execute(
            sa.select(Response.question_id, Response.respondent_id, Response.answer)
            .join(Respondent, Respondent.respondent_id == Response.respondent_id)
            .where(
                in_window,
                Response.question_id.in_(list(catalog)),
                Response.is_retest_of.is_(None),
                ~Respondent.is_flagged,
            )
            .order_by(Response.response_id)
        )
        for question_id, respondent_id, answer in honeypot_rows.tuples():
            answers.append(
                HoneypotAnswer(
                    question_id=question_id,
                    respondent_id=respondent_id,
                    passed=honeypots.evaluate(answer, expected[question_id]),
                )
            )

    original = aliased(Response)
    retest_rows = await session.execute(
        sa.select(
            Response.respondent_id,
            Response.type,
            Question.champion_c,
            original.answer,
            Response.answer,
        )
        .join(original, original.response_id == Response.is_retest_of)
        .join(Question, Question.question_id == Response.question_id)
        .join(Respondent, Respondent.respondent_id == Response.respondent_id)
        .where(in_window, Response.is_retest_of.is_not(None), ~Respondent.is_flagged)
        .order_by(Response.response_id)
    )
    pairs = [
        RetestPair(
            respondent_id=respondent_id,
            kind=_kind(QuestionType(kind), champion_c),
            consistent=retests.is_consistent(QuestionType(kind), first, repeat),
        )
        for respondent_id, kind, champion_c, first, repeat in retest_rows.tuples()
    ]

    excluded = await _excluded(session, patch_ids, params)
    get = app_settings.get
    settings = Settings(
        honeypot_min_attempts=int(await get(session, "quality.honeypot_min_attempts", 40)),
        fingerprint_max_identities=int(await get(session, "quality.fingerprint_max_identities", 5)),
        segment_min_respondents=int(await get(session, "aggregation.segment_min_respondents", 15)),
        segment_min_comparisons=int(await get(session, "aggregation.segment_min_comparisons", 300)),
    )
    return Extra(
        people=people,
        honeypots=catalog,
        honeypot_answers=answers,
        retests=pairs,
        active_honeypots=active_honeypots,
        excluded=excluded,
        settings=settings,
        patches=[p.version for p in patches],
    )


async def _excluded(session: AsyncSession, patch_ids: list[int], params: RunParams) -> Excluded:
    """Cuántas respuestas de la ventana deja afuera cada filtro, en cascada: una fila cuenta en el
    primero que la excluye. La suma más las de la corrida da el total de la ventana."""
    is_retest = Response.is_retest_of.is_not(None)
    is_honeypot = sa.and_(~is_retest, Question.is_honeypot)
    is_flagged = sa.and_(~is_retest, ~Question.is_honeypot, Respondent.is_flagged)
    low_trust = sa.and_(
        ~is_retest,
        ~Question.is_honeypot,
        ~Respondent.is_flagged,
        Respondent.trust_score < params.min_trust,
    )
    row = (
        await session.execute(
            sa.select(
                sa.func.count(),
                sa.func.count().filter(is_retest),
                sa.func.count().filter(is_honeypot),
                sa.func.count().filter(is_flagged),
                sa.func.count().filter(low_trust),
            )
            .select_from(Response)
            .join(Question, Question.question_id == Response.question_id)
            .join(Respondent, Respondent.respondent_id == Response.respondent_id)
            .where(Response.patch_id.in_(patch_ids))
        )
    ).one()
    total, retest, honeypot, flagged, trust = row
    return Excluded(window=total, retest=retest, honeypot=honeypot, flagged=flagged, trust=trust)
