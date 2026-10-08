"""`GET /questions/next` (`docs/12-api.md` §2.3)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.dependencies import CurrentSessionDep, SessionDep
from app.errors import ApiError
from app.schemas.questions import QuestionBatch
from app.services import sampler

router = APIRouter(prefix="/questions", tags=["questions"])

MIN_COUNT = 1
MAX_COUNT = 10
DEFAULT_COUNT = 5

#: A lo sumo tantos ids como caben en un lote: un cliente no puede tener más en cola que lo que le
#: entra en un pedido (`docs/12-api.md` §2.3, nota del 17/09).
MAX_QUEUED = MAX_COUNT


def parse_queued(raw: str | None) -> list[int]:
    """Los `question_id` de `queued=881,882`. Lanza `ValueError` si no es una lista válida."""
    if not raw:
        return []
    ids = [int(part) for part in raw.split(",")]
    if len(ids) > MAX_QUEUED or any(question_id <= 0 for question_id in ids):
        raise ValueError(raw)
    return list(dict.fromkeys(ids))


@router.get("/next", response_model=QuestionBatch)
async def next_questions(
    session: SessionDep,
    current: CurrentSessionDep,
    count: Annotated[int, Query()] = DEFAULT_COUNT,
    queued: Annotated[str | None, Query()] = None,
) -> QuestionBatch:
    """El próximo lote. Se piden de a lotes para que la interfaz no espere entre tarjeta y tarjeta.

    Lo elige el sampler completo de `docs/21-sampler.md`, con las honeypots y los retests
    intercalados de forma indistinguible (RF-202). Ver el docstring de `app/services/sampler.py`.

    `queued` son las preguntas que el cliente tiene en cola sin contestar. Sin ellas el servidor no
    sabe en qué posición cae cada pregunta nueva —y las cadencias de calidad se corren— ni cuáles
    no volver a mandar (ADR-020).
    """
    if not MIN_COUNT <= count <= MAX_COUNT:
        raise ApiError(
            "invalid_parameter",
            f"count must be between {MIN_COUNT} and {MAX_COUNT}",
            status.HTTP_400_BAD_REQUEST,
            "count",
        )
    try:
        queued_ids = parse_queued(queued)
    except ValueError as exc:
        raise ApiError(
            "invalid_parameter",
            f"queued must be a comma-separated list of up to {MAX_QUEUED} question ids",
            status.HTTP_400_BAD_REQUEST,
            "queued",
        ) from exc
    batch = await sampler.next_batch(session, current.respondent, count, queued=queued_ids)
    return QuestionBatch(questions=batch)
