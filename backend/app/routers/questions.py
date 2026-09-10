"""`GET /questions/next` (`docs/12-api.md` §2.3)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.dependencies import CurrentSessionDep, SessionDep
from app.errors import ApiError
from app.schemas.questions import QuestionBatch
from app.services import questions

router = APIRouter(prefix="/questions", tags=["questions"])

MIN_COUNT = 1
MAX_COUNT = 10
DEFAULT_COUNT = 5


@router.get("/next", response_model=QuestionBatch)
async def next_questions(
    session: SessionDep,
    current: CurrentSessionDep,
    count: Annotated[int, Query()] = DEFAULT_COUNT,
) -> QuestionBatch:
    """El próximo lote. Se piden de a lotes para que la interfaz no espere entre tarjeta y tarjeta.

    En la semana 2 devuelve sólo preguntas de tipo `pairwise_dimension`, sorteadas de forma
    uniforme: es el régimen de arranque en frío de ADR-012, y el sampler completo es de la
    semana 5. Ver el docstring de `app/services/questions.py`.
    """
    if not MIN_COUNT <= count <= MAX_COUNT:
        raise ApiError(
            "invalid_parameter",
            f"count must be between {MIN_COUNT} and {MAX_COUNT}",
            status.HTTP_400_BAD_REQUEST,
            "count",
        )
    batch = await questions.next_batch(session, current.respondent, count)
    return QuestionBatch(questions=batch)
