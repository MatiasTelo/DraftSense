"""Contrato de `POST /responses` (`docs/12-api.md` §2.4)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import is_absent


class ResponseIn(BaseModel):
    question_id: int
    #: La forma del `answer` depende del tipo real de la pregunta, no de lo que declare el
    #: cliente: se valida contra `questions.type` leído de la base (RF-108).
    answer: dict[str, Any]
    response_time_ms: int = Field(ge=0, lt=600_000)


class Feedback(BaseModel):
    """Se omite entero cuando el soporte es menor a 20 (ADR-012, RF-114).

    Cada tipo usa un subconjunto de campos: los de elección, `consensus` y
    `agreed_with_majority`; el tipo 2, `consensus_median` y `your_answer`. Los que no aplican no
    viajan, ni siquiera en `null` (`docs/12-api.md` §2.4).
    """

    consensus: dict[str, float] | None = Field(default=None, exclude_if=is_absent)
    #: Entero: la mediana sin ponderar de `answer_counts`, con el medio redondeado hacia arriba.
    consensus_median: int | None = Field(default=None, exclude_if=is_absent)
    your_answer: int | None = Field(default=None, exclude_if=is_absent)
    agreed_with_majority: bool | None = Field(default=None, exclude_if=is_absent)
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
