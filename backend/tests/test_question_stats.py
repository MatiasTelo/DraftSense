"""El job `refresh_question_stats` y el feedback de consenso que habilita.

Hasta la semana 3 `questions.answer_counts` no lo refrescaba nadie, así que `build_feedback`
devolvía `None` siempre y el panel de consenso de `docs/30-ux-flujos.md` §5.1 no se mostraba nunca.
Estos tests cubren las dos mitades: que el job calcule bien, y que el umbral de RF-114 y de ADR-012
se respete en los dos sentidos.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Champion, Dimension, Patch, Question, QuestionType, Response
from app.services import question_stats, sessions
from app.services import responses as responses_service
from app.services.question_stats import binary_entropy
from tests.conftest import requires_db


async def _question(
    db: AsyncSession,
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
    offset: int = 0,
) -> Question:
    low, high = sorted(c.champion_id for c in champions[offset : offset + 2])
    row = Question(
        type=QuestionType.PAIRWISE_DIMENSION,
        champion_a=low,
        champion_b=high,
        dimension_id=dimension.dimension_id,
        patch_id=patch.patch_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _answer_many(db: AsyncSession, question: Question, choices: list[str]) -> None:
    """Una respuesta por respondedor distinto.

    Tienen que ser distintos: `responses_one_per_question` impide que el mismo conteste dos veces
    la misma pregunta, que es justamente lo que garantiza que `answer_counts` cuente personas.
    """
    now = dt.datetime.now(dt.UTC)
    for i, choice in enumerate(choices):
        respondent, _ = await sessions.create(db, f"huella-{question.question_id}-{i}")
        await responses_service.record(db, respondent, question, {"choice": choice}, 2000, now)


# ------------------------------------------------------------------- la fórmula, sin base de datos


def test_entropia_maxima_con_el_par_dividido() -> None:
    """`docs/21-sampler.md` §3.2 — mitad y mitad es el caso de máxima incertidumbre."""
    assert binary_entropy(50, 50) == Decimal("1.0000")


def test_entropia_nula_con_acuerdo_total() -> None:
    assert binary_entropy(40, 0) == Decimal("0.0000")
    assert binary_entropy(0, 40) == Decimal("0.0000")


def test_entropia_dentro_del_rango_permitido() -> None:
    """`questions_entropy_range` rechaza todo valor fuera de [0,1], incluido 1.0000000000002."""
    for a in range(41):
        value = binary_entropy(a, 40 - a)
        assert value is not None
        assert Decimal("0") <= value <= Decimal("1")


def test_sin_respuestas_decisivas_la_entropia_es_desconocida() -> None:
    """`None` y no cero: la columna es nulable para distinguir «no hay datos» de «hay acuerdo»."""
    assert binary_entropy(0, 0) is None


# -------------------------------------------------------------------------------- el job, con base


@requires_db
async def test_el_job_puebla_los_denormalizados(
    db: AsyncSession, patch: Patch, champions: list[Champion], dimension: Dimension
) -> None:
    question = await _question(db, patch, champions, dimension)
    await _answer_many(db, question, ["a"] * 7 + ["b"] * 2 + ["unknown"])

    result = await question_stats.refresh(db)
    await db.refresh(question)

    assert result.patch == patch.version
    assert result.responses == 10
    assert question.answer_counts == {"a": 7, "b": 2, "unknown": 1}
    assert question.exposure_count == 10
    assert question.stats_refreshed_at is not None


@requires_db
async def test_el_unknown_cuenta_pero_no_entra_en_la_entropia(
    db: AsyncSession, patch: Patch, champions: list[Champion], dimension: Dimension
) -> None:
    """§3.2 — `unknown` no es una tercera opción: mide otra cosa y se exporta aparte."""
    question = await _question(db, patch, champions, dimension)
    await _answer_many(db, question, ["a"] * 5 + ["b"] * 5 + ["unknown"] * 20)

    await question_stats.refresh(db)
    await db.refresh(question)

    # Con los 20 `unknown` adentro del cálculo la entropía daría ~0.8, no 1.
    assert question.entropy == Decimal("1.0000")
    assert question.exposure_count == 30


@requires_db
async def test_una_pregunta_sin_respuestas_queda_explicitamente_vacia(
    db: AsyncSession, patch: Patch, champions: list[Champion], dimension: Dimension
) -> None:
    question = await _question(db, patch, champions, dimension)

    await question_stats.refresh(db)
    await db.refresh(question)

    assert question.answer_counts == {}
    assert question.exposure_count == 0
    assert question.entropy is None
    assert question.stats_refreshed_at is not None


@requires_db
async def test_el_refresco_es_idempotente(
    db: AsyncSession, patch: Patch, champions: list[Champion], dimension: Dimension
) -> None:
    """Recalcula desde cero, no acumula: correrlo dos veces tiene que dar lo mismo."""
    question = await _question(db, patch, champions, dimension)
    await _answer_many(db, question, ["a"] * 3 + ["b"])

    await question_stats.refresh(db)
    await db.refresh(question)
    first = (question.answer_counts, question.exposure_count, question.entropy)

    await question_stats.refresh(db)
    await db.refresh(question)

    assert (question.answer_counts, question.exposure_count, question.entropy) == first


@requires_db
async def test_las_preguntas_de_otro_parche_no_se_tocan(
    db: AsyncSession, patch: Patch, champions: list[Champion], dimension: Dimension
) -> None:
    """ADR-004 — el crudo conserva su parche y el job sólo mira el vigente."""
    question = await _question(db, patch, champions, dimension)
    await _answer_many(db, question, ["a"] * 4)

    old = Patch(version="98.98", released_at=dt.date(2026, 8, 1), is_current=False)
    db.add(old)
    await db.commit()
    await db.execute(
        sa.update(Question)
        .where(Question.question_id == question.question_id)
        .values(patch_id=old.patch_id)
    )
    await db.commit()

    result = await question_stats.refresh(db)
    await db.refresh(question)

    assert result.questions == 0
    assert question.answer_counts == {}


# -------------------------------------------------------- el umbral de consenso — RF-114 · ADR-012


@requires_db
async def test_sin_soporte_no_hay_feedback(
    db: AsyncSession, patch: Patch, champions: list[Champion], dimension: Dimension
) -> None:
    """CA-503 — debajo de `sampler.consensus_threshold` la interfaz dice «sos de los primeros»."""
    question = await _question(db, patch, champions, dimension)
    await _answer_many(db, question, ["a"] * 19)

    await question_stats.refresh(db)
    await db.refresh(question)

    assert await responses_service.build_feedback(db, question, {"choice": "a"}) is None


@requires_db
async def test_con_soporte_aparece_el_consenso(
    db: AsyncSession, patch: Patch, champions: list[Champion], dimension: Dimension
) -> None:
    question = await _question(db, patch, champions, dimension)
    await _answer_many(db, question, ["a"] * 15 + ["b"] * 4 + ["unknown"])

    await question_stats.refresh(db)
    await db.refresh(question)

    agreed = await responses_service.build_feedback(db, question, {"choice": "a"})
    assert agreed is not None
    assert agreed.sample_size == 20
    assert agreed.agreed_with_majority is True
    assert agreed.consensus == {"a": 0.75, "b": 0.2, "unknown": 0.05}

    # CA-504 — la discrepancia es un dato, no un error: se informa igual y sin marca de incorrecto.
    dissenting = await responses_service.build_feedback(db, question, {"choice": "b"})
    assert dissenting is not None
    assert dissenting.agreed_with_majority is False


@requires_db
async def test_el_feedback_no_filtra_nada_de_la_pregunta(
    db: AsyncSession, patch: Patch, champions: list[Champion], dimension: Dimension
) -> None:
    """`docs/12-api.md` §1.4 — el consenso sale de `answer_counts` y de nada más."""
    question = await _question(db, patch, champions, dimension)
    await _answer_many(db, question, ["a"] * 20)

    await question_stats.refresh(db)
    await db.refresh(question)

    feedback = await responses_service.build_feedback(db, question, {"choice": "a"})
    assert feedback is not None
    assert set(feedback.model_dump()) <= {
        "consensus",
        "consensus_median",
        "your_answer",
        "agreed_with_majority",
        "sample_size",
    }


@requires_db
async def test_el_job_no_mezcla_preguntas(
    db: AsyncSession, patch: Patch, champions: list[Champion], dimension: Dimension
) -> None:
    first = await _question(db, patch, champions, dimension)
    second = await _question(db, patch, champions, dimension, offset=2)
    await _answer_many(db, first, ["a", "a", "b"])
    await _answer_many(db, second, ["b"] * 5)

    result = await question_stats.refresh(db)
    await db.refresh(first)
    await db.refresh(second)

    assert result.questions == 2
    assert result.responses == 8
    assert first.answer_counts == {"a": 2, "b": 1}
    assert second.answer_counts == {"b": 5}
    assert (
        await db.execute(
            sa.select(sa.func.count())
            .select_from(Response)
            .where(Response.question_id == second.question_id)
        )
    ).scalar_one() == 5
