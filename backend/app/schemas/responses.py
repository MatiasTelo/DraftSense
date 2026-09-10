"""Contrato de `POST /responses` (`docs/12-api.md` §2.4)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResponseIn(BaseModel):
    question_id: int
    #: La forma del `answer` depende del tipo real de la pregunta, no de lo que declare el
    #: cliente: se valida contra `questions.type` leído de la base (RF-108).
    answer: dict[str, Any]
    response_time_ms: int = Field(ge=0, lt=600_000)


class Feedback(BaseModel):
    """Se omite entero cuando el soporte es menor a 20 (ADR-012, RF-114)."""

    consensus: dict[str, float] | None = None
    consensus_median: float | None = None
    your_answer: float | None = None
    agreed_with_majority: bool | None = None
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
