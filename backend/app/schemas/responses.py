"""Contrato de `POST /responses` (`docs/12-api.md` §2.4)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import is_absent

#: El mayor `bigint` de Postgres. Un id más grande no puede existir, y si llegara a la consulta
#: asyncpg lo rechaza con un error de datos que el manejador de `DBAPIError` informa como
#: `503 database_unavailable`: la base estaría «caída» para un simple id mal escrito.
MAX_ID = 2**63 - 1


class ResponseIn(BaseModel):
    question_id: int = Field(ge=-MAX_ID, le=MAX_ID)
    #: Sólo el tipo 1: el ranking servido, cuyo ancla tiene que ser `question_id` (ADR-022).
    ranking_id: int | None = Field(default=None, ge=-MAX_ID, le=MAX_ID)
    #: La forma del `answer` depende del tipo real de la pregunta, no de lo que declare el
    #: cliente: se valida contra `questions.type` leído de la base (RF-108).
    answer: dict[str, Any]
    response_time_ms: int = Field(ge=0, lt=600_000)


class Feedback(BaseModel):
    """Se omite entero cuando el soporte es menor a 20 (ADR-012, RF-114).

    Cada tipo usa un subconjunto de campos: los de elección, `consensus` y
    `agreed_with_majority`; el tipo 2, `consensus_median` y `your_answer`; el tipo 1, que es un
    ranking, `pairs_agreed` y `pairs_compared` (ADR-022); el tipo 5, `trait_shares`,
    `traits_agreed` y `traits_compared` (nota del 29/10). Los que no aplican no viajan, ni siquiera
    en `null` (`docs/12-api.md` §2.4).
    """

    consensus: dict[str, float] | None = Field(default=None, exclude_if=is_absent)
    #: Entero: la mediana sin ponderar de `answer_counts`, con el medio redondeado hacia arriba.
    consensus_median: int | None = Field(default=None, exclude_if=is_absent)
    your_answer: int | None = Field(default=None, exclude_if=is_absent)
    agreed_with_majority: bool | None = Field(default=None, exclude_if=is_absent)
    #: Tipo 1: en cuántos de los pares con soporte coincide el orden con la mayoría.
    pairs_agreed: int | None = Field(default=None, exclude_if=is_absent)
    #: Tipo 1: cuántos pares del ranking tienen al menos `sampler.consensus_threshold` respuestas.
    pairs_compared: int | None = Field(default=None, exclude_if=is_absent)
    #: Tipo 5: qué fracción de la comunidad marcó cada atributo activo.
    trait_shares: dict[str, float] | None = Field(default=None, exclude_if=is_absent)
    #: Tipo 5: en cuántos atributos coincide con la mayoría, y cuántos se compararon.
    traits_agreed: int | None = Field(default=None, exclude_if=is_absent)
    traits_compared: int | None = Field(default=None, exclude_if=is_absent)
    sample_size: int


class Progress(BaseModel):
    answers_count: int
    current_streak: int
    best_streak: int
    current_day_streak: int
    best_day_streak: int
    agreement_rate: float


class RecordedResponse(BaseModel):
    recorded: bool
    feedback: Feedback | None
    progress: Progress
