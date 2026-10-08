"""Registro de respuestas: rate limit, inserción append-only, calidad y feedback de consenso.

Es el camino crítico del sistema (`docs/10-arquitectura.md` §3) y tiene 150 ms de presupuesto.
Nada de lo que hace agrega: cuenta filas sobre índices, inserta una y hace aritmética sobre la
fila del respondedor.

Desde el 08/10 el tipo 1 es un ranking de cinco campeones que se guarda como diez filas, una por
par (ADR-022, `record_ranking`). Para la persona sigue siendo una respuesta: lo que cuenta
respuestas —el rate limit, `answers_count`, las rachas— cuenta envíos (`submissions`).

Desde la semana 5 hace también el paso 5 de la arquitectura: si la pregunta era honeypot o
retest, actualiza los contadores de calidad y recalcula el trust en la misma transacción
(`docs/22-calidad-de-datos.md` §7.2). El retest lo reconoce el servidor, no el cliente (ADR-020).
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.models import Question, QuestionType, Ranking, Respondent, Response
from app.schemas.responses import Feedback, Progress
from app.services import (
    app_settings,
    honeypots,
    question_stats,
    questions,
    rankings,
    retests,
    streaks,
    submissions,
    trust,
)
from app.services.answers import UNKNOWN_CHOICE

#: Los dos límites del contrato (`docs/12-api.md` §4). Son holgados para una persona —una
#: respuesta cada 5 a 10 segundos son unas 10 por minuto— y cortan el scripting trivial.
PER_MINUTE = 40
PER_DAY = 1500

_rng = random.Random()


class RateLimitError(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"retry after {retry_after}s")
        self.retry_after = retry_after


@dataclass(slots=True)
class RateLimitState:
    """Lo que viaja en las cabeceras `X-RateLimit-*` de toda respuesta del endpoint."""

    limit: int
    remaining: int
    reset: int


async def _count_since(
    session: AsyncSession, respondent: Respondent, since: dt.datetime
) -> int:
    """Envíos desde `since`: un ranking del tipo 1 cuenta uno, aunque sean diez filas."""
    return (
        await session.execute(
            submissions.heads(sa.select(sa.func.count()).select_from(Response))
            .where(
                Response.respondent_id == respondent.respondent_id,
                Response.created_at > since,
            )
        )
    ).scalar_one()


async def check_rate_limit(
    session: AsyncSession, respondent: Respondent, now: dt.datetime
) -> RateLimitState:
    """Ventana deslizante contando sobre `responses_by_respondent`.

    Sin Redis ni contador en memoria: además de ahorrar infraestructura, evita que el límite se
    reinicie en cada despliegue (`docs/12-api.md` §4). Con el índice es un recorrido de unas
    pocas decenas de filas.

    El límite por hash de IP que menciona §4 **no está implementado**: `responses` no guarda
    ninguna columna derivada de la IP, y agregarla contradiría RNF-05. Queda el límite por
    respondedor, que es el que describe el párrafo de implementación del mismo documento.
    """
    minute_ago = now - dt.timedelta(minutes=1)
    day_ago = now - dt.timedelta(days=1)

    in_minute = await _count_since(session, respondent, minute_ago)
    if in_minute >= PER_MINUTE:
        oldest = (
            await session.execute(
                submissions.heads(
                    sa.select(sa.func.min(Response.created_at)).select_from(Response)
                ).where(
                    Response.respondent_id == respondent.respondent_id,
                    Response.created_at > minute_ago,
                )
            )
        ).scalar_one()
        retry_after = max(1, int((oldest + dt.timedelta(minutes=1) - now).total_seconds()))
        raise RateLimitError(retry_after)

    in_day = await _count_since(session, respondent, day_ago)
    if in_day >= PER_DAY:
        raise RateLimitError(int(dt.timedelta(days=1).total_seconds()))

    return RateLimitState(
        limit=PER_MINUTE,
        remaining=PER_MINUTE - in_minute - 1,
        reset=int((now + dt.timedelta(minutes=1)).timestamp()),
    )


async def claim_retest(
    session: AsyncSession, respondent: Respondent, question: Question
) -> Response | None:
    """La respuesta original, si esta respuesta es el retest que el sampler dejó pendiente.

    La marca se limpia con un `UPDATE` condicional y no asignando el atributo: si dos envíos de
    la misma respuesta llegan juntos —un doble toque—, el segundo espera el bloqueo de la fila,
    ya no encuentra la marca, se inserta como respuesta común y el índice
    `responses_one_per_question` lo rechaza con `409` (ADR-020, CA-204).
    """
    pending = respondent.pending_retest_of
    if pending is None:
        return None
    original = await session.get(Response, pending)
    if (
        original is None
        or original.question_id != question.question_id
        or original.respondent_id != respondent.respondent_id
    ):
        return None
    claimed = (
        await session.execute(
            sa.update(Respondent)
            .where(
                Respondent.respondent_id == respondent.respondent_id,
                Respondent.pending_retest_of == pending,
            )
            .values(pending_retest_of=None)
            .returning(Respondent.respondent_id)
            .execution_options(synchronize_session=False)
        )
    ).first()
    if claimed is None:
        return None
    # La fila ya quedó en NULL: se refleja en el objeto sin que el flush lo vuelva a escribir.
    set_committed_value(respondent, "pending_retest_of", None)
    return original


async def apply_quality(
    session: AsyncSession,
    respondent: Respondent,
    question: Question,
    answer: dict[str, Any],
    original: Response | None,
    position: int,
    rng: random.Random,
) -> None:
    """Contadores de calidad, cadencias y trust, si la pregunta era honeypot o retest. Sin commit.

    Una honeypot contestada `unknown` no suma intento (22 §3.5) pero abre la ventana siguiente:
    si no la abriera, la persona recibiría honeypots seguidas y el mecanismo se delataría.
    """
    touched = False
    if respondent.pending_honeypot == question.question_id:
        # Contestada, deja de bloquear: el próximo lote ya puede elegir otra cuando toque. Se
        # limpia aunque la honeypot se haya retirado mientras estaba en la cola.
        respondent.pending_honeypot = None
    if question.is_honeypot:
        outcome = honeypots.evaluate(answer, question.expected_answer)
        if outcome is not None:
            respondent.honeypot_attempts += 1
            respondent.honeypot_passed += int(outcome)
        low, high = await app_settings.get(session, "quality.honeypot_every", [10, 15])
        respondent.next_honeypot_at = position + rng.randint(int(low), int(high))
        touched = True
    if original is not None:
        consistent = retests.is_consistent(question.type, original.answer, answer)
        if consistent is not None:
            respondent.retest_pairs += 1
            respondent.retest_consistent += int(consistent)
        every = await app_settings.get(session, "quality.retest_every", 30)
        respondent.next_retest_at = position + int(every)
        touched = True
    if touched:
        trust.refresh(respondent, await trust.TrustParams.load(session))


async def record(
    session: AsyncSession,
    respondent: Respondent,
    question: Question,
    answer: dict[str, Any],
    response_time_ms: int,
    now: dt.datetime,
    rng: random.Random | None = None,
) -> Response:
    """Inserta la respuesta y actualiza los contadores, en una sola transacción.

    `type` y `patch_id` se copian de la pregunta: son redundantes a propósito —permiten expresar
    la validación del `answer` como restricción de tabla y que el pipeline recorra por parche y
    tipo sin tocar `questions`— y la consistencia la garantiza este INSERT
    (`docs/11-modelo-de-datos.md` §3.9).

    La posición se toma **antes** de sumar la respuesta: es el índice de esta respuesta en la
    historia del respondedor (ADR-020). El trust se recalcula **después**, con el volumen que ya
    la incluye, que es el que usa el denominador de `d` (22 §7.1).
    """
    position = respondent.answers_count
    original = await claim_retest(session, respondent, question)
    response = Response(
        respondent_id=respondent.respondent_id,
        question_id=question.question_id,
        type=question.type,
        patch_id=question.patch_id,
        answer=answer,
        response_time_ms=response_time_ms,
        is_retest_of=original.response_id if original is not None else None,
    )
    session.add(response)
    await streaks.apply(session, respondent, now)
    await apply_quality(session, respondent, question, answer, original, position, rng or _rng)
    await session.commit()
    await session.refresh(response)
    return response


@dataclass(frozen=True, slots=True)
class RecordedRanking:
    """Lo que el feedback necesita de un ranking guardado: cada par y lo que dijo de él."""

    pairs: list[tuple[Question, str]]
    unknown: bool


async def record_ranking(
    session: AsyncSession,
    respondent: Respondent,
    ranking: Ranking,
    anchor: Question,
    order: list[int] | None,
    response_time_ms: int,
    now: dt.datetime,
    rng: random.Random | None = None,
) -> RecordedRanking:
    """Guarda un ranking del tipo 1 como diez filas, una por par, en una sola transacción.

    `order` va de más a menos; `None` es *Not sure*, que se guarda como `unknown` en los diez pares
    para que siga alimentando `unknown_rate` (ADR-022).

    - **El ancla va primero y con un INSERT común**: si ya estaba contestada, el índice
      `responses_one_per_question` levanta el 409 de siempre y no se guarda nada. Si era el retest
      pendiente, lleva `is_retest_of`.
    - **Los otros nueve, con `ON CONFLICT DO NOTHING`**: un par que la persona ya había contestado
      en otro ranking se ignora y se guardan los demás.
    - **Un par no ancla que es honeypot no se guarda**: una honeypot sólo se contesta como ancla y
      con su cadencia (22 §3.7). El sampler ya intenta evitarlos al sortear.
    - Honeypot, retest, cadencias, rachas y `answers_count` se aplican **una vez**, sobre el ancla.
    """
    position = respondent.answers_count
    original = await claim_retest(session, respondent, anchor)
    by_pair = await questions.materialize_many(
        session, ranking.patch_id, rankings.combinations_of(ranking.champions, ranking.dimension_id)
    )
    said = rankings.choices_from_order(order) if order is not None else {}

    def answer_for(question: Question) -> dict[str, str]:
        assert question.champion_b is not None
        choice = said.get((question.champion_a, question.champion_b), UNKNOWN_CHOICE)
        return {"choice": choice}

    def row(question: Question) -> dict[str, Any]:
        return {
            "respondent_id": respondent.respondent_id,
            "question_id": question.question_id,
            "type": question.type,
            "patch_id": question.patch_id,
            "answer": answer_for(question),
            "response_time_ms": response_time_ms,
            "ranking_id": ranking.ranking_id,
        }

    anchor_answer = answer_for(anchor)
    session.add(
        Response(
            **row(anchor),
            is_retest_of=original.response_id if original is not None else None,
        )
    )
    await session.flush()

    others = [
        q
        for q in by_pair.values()
        if q.question_id != anchor.question_id and not q.is_honeypot
    ]
    if others:
        await session.execute(
            pg_insert(Response)
            .values([row(q) for q in others])
            .on_conflict_do_nothing(
                index_elements=["respondent_id", "question_id"],
                index_where=Response.is_retest_of.is_(None),
            )
        )
    ranking.submitted_order = order
    await streaks.apply(session, respondent, now)
    await apply_quality(
        session, respondent, anchor, anchor_answer, original, position, rng or _rng
    )
    await session.commit()
    return RecordedRanking(
        pairs=[(q, answer_for(q)["choice"]) for q in by_pair.values()],
        unknown=order is None,
    )


async def build_ranking_feedback(
    session: AsyncSession, recorded: RecordedRanking
) -> Feedback | None:
    """En cuántos pares del ranking coincide el orden con la mayoría (ADR-022).

    Cuentan sólo los pares con al menos `sampler.consensus_threshold` respuestas, por la misma
    razón que en los demás tipos: por debajo, la «mayoría» es ruido. Sin ningún par con soporte,
    o con *Not sure*, no hay feedback y la interfaz explica que todavía no hay respuestas
    suficientes (RF-114).
    """
    if recorded.unknown:
        return None
    threshold = await app_settings.get(session, "sampler.consensus_threshold", 20)
    compared = agreed = sample_size = 0
    for question, choice in recorded.pairs:
        counts: dict[str, int] = question.answer_counts or {}
        total = sum(counts.values())
        if total == 0 or total < threshold:
            continue
        compared += 1
        sample_size += total
        agreed += int(choice == max(counts, key=lambda k: counts[k]))
    if compared == 0:
        return None
    return Feedback(pairs_agreed=agreed, pairs_compared=compared, sample_size=sample_size)


async def build_feedback(
    session: AsyncSession, question: Question, answer: dict[str, Any]
) -> Feedback | None:
    """El consenso de la comunidad, o `None` si todavía no hay soporte suficiente.

    Sale del campo denormalizado `questions.answer_counts`, que refresca cada 15 minutos el job
    `refresh_question_stats`: calcularlo en vivo sería un GROUP BY en el camino crítico. Puede
    estar levemente desactualizado, lo cual es irrelevante para un mensaje motivacional.

    Con menos de `sampler.consensus_threshold` respuestas se devuelve `None` y la interfaz dice
    *"you're one of the first to answer this"*, para no anclar a los primeros sobre ruido
    (ADR-012, RF-114). Al arrancar el piloto todas las preguntas están en ese caso.

    La forma depende del tipo (`docs/12-api.md` §2.4). En el tipo 2 el consenso es la mediana de
    los minutos. En los tipos de elección es el reparto de opciones, y el acuerdo se mide contra
    la opción exacta más votada: en el tipo 3, *wins hard* y *wins slightly* del mismo campeón son
    respuestas distintas.
    """
    threshold = await app_settings.get(session, "sampler.consensus_threshold", 20)
    counts: dict[str, int] = question.answer_counts or {}
    sample_size = sum(counts.values())
    # El `== 0` cubre un umbral configurado en 0: sin él, `max()` sobre un dict vacío revienta.
    if sample_size == 0 or sample_size < threshold:
        return None

    if question.type is QuestionType.PEAK_TIMING:
        return Feedback(
            consensus_median=question_stats.peak_median(counts),
            your_answer=answer["minute"],
            sample_size=sample_size,
        )

    consensus = {key: value / sample_size for key, value in counts.items()}
    majority = max(counts, key=lambda k: counts[k])
    return Feedback(
        consensus=consensus,
        agreed_with_majority=answer.get("choice") == majority,
        sample_size=sample_size,
    )


def build_progress(respondent: Respondent, agreement_rate: float) -> Progress:
    return Progress(
        answers_count=respondent.answers_count,
        current_streak=respondent.current_streak,
        best_streak=respondent.best_streak,
        current_day_streak=respondent.current_day_streak,
        best_day_streak=respondent.best_day_streak,
        agreement_rate=agreement_rate,
    )
