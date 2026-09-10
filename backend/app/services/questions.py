"""Entrega de preguntas — versión reducida de la semana 2.

**Esto NO es el sampler.** El sampler completo —función de prioridad por escasez, entropía,
cobertura y puentes, exploración con epsilon, honeypots y retests— es el entregable de la semana 5
y está especificado en `docs/21-sampler.md` §10. Acá está sólo lo que hace falta para que el
primer tipo de pregunta funcione de punta a punta:

- un único tipo, `pairwise_dimension`, que es el orden que fija `docs/20-tipos-de-pregunta.md` §8;
- sorteo uniforme sobre el pool habilitado, que es literalmente el régimen de arranque en frío que
  manda [ADR-012] mientras una pregunta tiene menos de `sampler.cold_threshold` respuestas — y al
  arrancar el piloto **todas** están en ese caso;
- generación bajo demanda: la pregunta se materializa cuando se la sortea, nunca se precomputa el
  producto cartesiano (RF-111).

Cuando llegue la semana 5, lo que se agrega es la rama de explotación; esta rama se conserva.
"""

from __future__ import annotations

import random

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Champion, Dimension, Patch, Question, QuestionType, Respondent, Response
from app.schemas.questions import ChampionRef, Help, PairwiseDimensionQuestion, Side
from app.services import app_settings

#: Etiqueta de la opción de escape. El "no sé" es información real —alimenta `D_unknown_rate`—
#: y por eso es una opción explícita y no la ausencia de respuesta.
UNKNOWN_LABEL = "Not sure"


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


async def _materialize(
    session: AsyncSession, *, patch_id: int, dimension_id: int, champion_a: int, champion_b: int
) -> Question:
    """Devuelve la pregunta, creándola si es la primera vez que se sortea (RF-111).

    El `ON CONFLICT DO NOTHING` más el `SELECT` posterior es lo que hace la operación segura
    entre peticiones simultáneas: el índice único `questions_identity` decide, no el código.
    """
    identity = (
        Question.type == QuestionType.PAIRWISE_DIMENSION,
        Question.patch_id == patch_id,
        Question.dimension_id == dimension_id,
        Question.champion_a == champion_a,
        Question.champion_b == champion_b,
    )
    existing = (await session.execute(sa.select(Question).where(*identity))).scalar_one_or_none()
    if existing is not None:
        return existing

    await session.execute(
        pg_insert(Question)
        .values(
            type=QuestionType.PAIRWISE_DIMENSION,
            patch_id=patch_id,
            dimension_id=dimension_id,
            champion_a=champion_a,
            champion_b=champion_b,
        )
        .on_conflict_do_nothing()
    )
    await session.commit()
    return (await session.execute(sa.select(Question).where(*identity))).scalar_one()


async def next_batch(
    session: AsyncSession, respondent: Respondent, count: int
) -> list[PairwiseDimensionQuestion]:
    """Sortea `count` preguntas distintas y las devuelve ya renderizadas."""
    patch = await current_patch(session)
    champions = await _enabled_champions(session)
    dimensions = await _active_dimensions(session)
    if patch is None or len(champions) < 2 or not dimensions:
        return []

    retries = await app_settings.get(session, "sampler.max_rejection_retries", 10)
    answered = await _answered_question_ids(session, respondent)
    by_id = {c.champion_id: c for c in champions}

    chosen: list[Question] = []
    seen: set[int] = set()
    for _ in range(count):
        for _ in range(retries):
            dimension = random.choice(dimensions)
            a, b = random.sample(champions, 2)
            # El orden canónico es parte de la identidad de la pregunta: (A,B) y (B,A) son la
            # misma y el CHECK `questions_canonical_order` lo impone.
            low, high = sorted((a.champion_id, b.champion_id))
            question = await _materialize(
                session,
                patch_id=patch.patch_id,
                dimension_id=dimension.dimension_id,
                champion_a=low,
                champion_b=high,
            )
            if question.question_id in answered or question.question_id in seen:
                continue
            seen.add(question.question_id)
            chosen.append(question)
            break

    by_dimension = {d.dimension_id: d for d in dimensions}
    return [render(q, by_dimension[q.dimension_id], by_id) for q in chosen if q.dimension_id]


def champion_ref(champion: Champion) -> ChampionRef:
    return ChampionRef(
        id=champion.champion_id,
        key=champion.riot_key,
        name=champion.display_name,
        image_url=champion.image_url,
    )


def render(
    question: Question, dimension: Dimension, champions: dict[int, Champion]
) -> PairwiseDimensionQuestion:
    """El enunciado ya compuesto, como exige `docs/12-api.md` §1.1.

    El texto sale de `dimensions`, no del código: agregar una dimensión es insertar una fila
    (RF-603, CA-601). El cliente no conoce ninguna plantilla.
    """
    assert question.champion_b is not None
    return PairwiseDimensionQuestion(
        question_id=question.question_id,
        prompt=dimension.prompt_en,
        help=Help(label=dimension.label_en, text=dimension.description_en),
        options=[
            Side(key="a", champions=[champion_ref(champions[question.champion_a])]),
            Side(key="b", champions=[champion_ref(champions[question.champion_b])]),
            Side(key="unknown", label=UNKNOWN_LABEL, champions=[]),
        ],
    )
