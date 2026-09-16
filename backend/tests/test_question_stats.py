"""El job `refresh_question_stats` y el feedback de consenso que habilita.

Hasta la semana 3 `questions.answer_counts` no lo refrescaba nadie, así que `build_feedback`
devolvía `None` siempre y el panel de consenso de `docs/30-ux-flujos.md` §5.1 no se mostraba nunca.
Estos tests cubren las dos mitades: que el job calcule bien, y que el umbral de RF-114 y de ADR-012
se respete en los dos sentidos. Desde la semana 4 cubren también el tipo 2, cuyo consenso es una
mediana, y la variante 1v1 del tipo 3.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Champion, Dimension, LaneRole, Patch, Question, QuestionType, Response
from app.services import question_stats, sessions
from app.services import responses as responses_service
from app.services.question_stats import (
    binary_entropy,
    lane_entropy,
    peak_entropy,
    peak_median,
)
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


async def _typed_question(
    db: AsyncSession, patch: Patch, champions: list[Champion], question_type: QuestionType
) -> Question:
    """Una pregunta de tipo 2 o de tipo 3 (1v1), con la forma que exige `questions_shape`."""
    low, high = sorted(c.champion_id for c in champions[:2])
    if question_type is QuestionType.PEAK_TIMING:
        row = Question(type=question_type, champion_a=low, patch_id=patch.patch_id)
    else:
        row = Question(
            type=question_type,
            champion_a=low,
            champion_b=high,
            role=LaneRole.MID,
            patch_id=patch.patch_id,
        )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _answer_all(db: AsyncSession, question: Question, answers: list[dict[str, Any]]) -> None:
    """Una respuesta por respondedor distinto.

    Tienen que ser distintos: `responses_one_per_question` impide que el mismo conteste dos veces
    la misma pregunta, que es justamente lo que garantiza que `answer_counts` cuente personas.
    """
    now = dt.datetime.now(dt.UTC)
    for i, answer in enumerate(answers):
        respondent, _ = await sessions.create(db, f"huella-{question.question_id}-{i}")
        await responses_service.record(db, respondent, question, answer, 2000, now)


async def _answer_many(db: AsyncSession, question: Question, choices: list[str]) -> None:
    await _answer_all(db, question, [{"choice": choice} for choice in choices])


async def _answer_minutes(db: AsyncSession, question: Question, minutes: list[int]) -> None:
    await _answer_all(db, question, [{"minute": minute} for minute in minutes])


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


def test_matchup_entropia_colapsa_los_cinco_niveles() -> None:
    """§3.2 — la entropía del tipo 3 mide desacuerdo sobre quién gana, no sobre el margen."""
    split = {"a_strong": 10, "a_slight": 10, "even": 10, "b_slight": 5, "b_strong": 5}
    collapsed = {"a_strong": 20, "even": 10, "b_strong": 10}
    assert lane_entropy(split) == lane_entropy(collapsed)

    # Un tercio para cada resultado es la máxima incertidumbre posible.
    assert lane_entropy({"a_strong": 5, "a_slight": 5, "even": 10, "b_strong": 10}) == Decimal(
        "1.0000"
    )
    # Todos dicen que gana A, aunque discrepen en cuánto: no hay desacuerdo que medir.
    assert lane_entropy({"a_strong": 7, "a_slight": 3}) == Decimal("0.0000")


def test_matchup_sin_respuestas_la_entropia_es_desconocida() -> None:
    assert lane_entropy({}) is None


def test_pico_entropia_escala_el_rango_intercuartil() -> None:
    """§3.2 — `min(1, IQR/12)`, con cuartiles de interpolación lineal: Q1 = 23 y Q3 = 29."""
    assert peak_entropy({"20": 1, "26": 1, "32": 1}) == Decimal("0.5000")


def test_pico_entropia_satura_en_uno() -> None:
    assert peak_entropy({"0": 1, "40": 1}) == Decimal("1.0000")
    assert peak_entropy({"27": 30}) == Decimal("0.0000")


def test_pico_con_menos_de_dos_respuestas_la_entropia_es_desconocida() -> None:
    assert peak_entropy({}) is None
    assert peak_entropy({"27": 1}) is None


def test_la_mediana_del_pico_redondea_el_medio_hacia_arriba() -> None:
    """`docs/12-api.md` §2.4 — 24,5 es 25. `round()` daría 24, porque redondea al par."""
    assert peak_median({"24": 1, "25": 1}) == 25
    assert peak_median({"26": 1, "27": 1}) == 27
    assert peak_median({}) is None


def test_la_mediana_del_pico_trata_los_minutos_como_numeros() -> None:
    """Las claves del `jsonb` son texto: tomadas así, la mediana de "9", "10" y "30" sería "30"."""
    assert peak_median({"9": 1, "10": 1, "30": 1}) == 10


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


# ------------------------------------------------------------------------ tipos 2 y 3, con base


@requires_db
async def test_el_job_cubre_los_tipos_2_y_3(
    db: AsyncSession, patch: Patch, champions: list[Champion]
) -> None:
    """El histograma de minutos, los cinco niveles y la entropía propia de cada tipo."""
    peak = await _typed_question(db, patch, champions, QuestionType.PEAK_TIMING)
    lane = await _typed_question(db, patch, champions, QuestionType.LANE_MATCHUP)
    await _answer_minutes(db, peak, [25, 25, 30])
    await _answer_many(db, lane, ["a_strong", "a_strong", "even"])

    result = await question_stats.refresh(db)
    await db.refresh(peak)
    await db.refresh(lane)

    assert result.questions == 2
    assert result.responses == 6
    assert peak.answer_counts == {"25": 2, "30": 1}
    assert peak.exposure_count == 3
    # Q1 = 25 y Q3 = 27,5: IQR 2,5 sobre 12.
    assert peak.entropy == Decimal("0.2083")
    assert lane.answer_counts == {"a_strong": 2, "even": 1}
    assert lane.exposure_count == 3
    assert lane.entropy == Decimal("0.5794")


@requires_db
async def test_con_soporte_el_pico_devuelve_la_mediana(
    db: AsyncSession, patch: Patch, champions: list[Champion]
) -> None:
    """`docs/12-api.md` §2.4 — mediana y respuesta propia, sin claves de los tipos de elección."""
    question = await _typed_question(db, patch, champions, QuestionType.PEAK_TIMING)
    await _answer_minutes(db, question, [25] * 5 + [26] * 6 + [27] * 5 + [30] * 4)

    await question_stats.refresh(db)
    await db.refresh(question)

    feedback = await responses_service.build_feedback(db, question, {"minute": 27})
    assert feedback is not None
    assert feedback.model_dump() == {
        "consensus_median": 26,
        "your_answer": 27,
        "sample_size": 20,
    }


@requires_db
async def test_sin_soporte_el_pico_no_tiene_feedback(
    db: AsyncSession, patch: Patch, champions: list[Champion]
) -> None:
    question = await _typed_question(db, patch, champions, QuestionType.PEAK_TIMING)
    await _answer_minutes(db, question, [20] * 19)

    await question_stats.refresh(db)
    await db.refresh(question)

    assert await responses_service.build_feedback(db, question, {"minute": 20}) is None


@requires_db
async def test_el_acuerdo_del_matchup_es_exacto_sobre_los_cinco_niveles(
    db: AsyncSession, patch: Patch, champions: list[Champion]
) -> None:
    """*Wins hard* no coincide con *wins slightly*, aunque los dos digan que gana el mismo."""
    question = await _typed_question(db, patch, champions, QuestionType.LANE_MATCHUP)
    await _answer_many(db, question, ["a_slight"] * 12 + ["a_strong"] * 8)

    await question_stats.refresh(db)
    await db.refresh(question)

    hard = await responses_service.build_feedback(db, question, {"choice": "a_strong"})
    assert hard is not None
    assert hard.agreed_with_majority is False
    assert hard.consensus == {"a_slight": 0.6, "a_strong": 0.4}

    slight = await responses_service.build_feedback(db, question, {"choice": "a_slight"})
    assert slight is not None
    assert slight.agreed_with_majority is True
