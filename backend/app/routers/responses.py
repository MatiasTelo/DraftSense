"""`POST /responses` (`docs/12-api.md` §2.4)."""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from fastapi import APIRouter, status
from fastapi import Response as HttpResponse

from app.dependencies import CurrentSessionDep, SessionDep
from app.errors import ApiError
from app.models import Question, QuestionType
from app.schemas.responses import RecordedResponse, ResponseIn
from app.services import answers, profile, responses

router = APIRouter(tags=["responses"])


@router.post("/responses", response_model=RecordedResponse, status_code=status.HTTP_201_CREATED)
async def create_response(
    payload: ResponseIn,
    http_response: HttpResponse,
    session: SessionDep,
    current: CurrentSessionDep,
) -> RecordedResponse:
    """Registra una respuesta.

    El orden de los pasos es el de `docs/10-arquitectura.md` §3.6 y no es arbitrario: primero se
    valida la forma, después el rate limit y recién entonces se inserta. Validar después de
    contar dejaría que una respuesta malformada consumiera cuota.

    El `409` por duplicado **no se anticipa con un SELECT**: lo levanta el índice único parcial
    `responses_one_per_question` y lo traduce el manejador de `IntegrityError`. Con un chequeo
    previo, dos peticiones simultáneas pasarían las dos.
    """
    question = (
        await session.execute(
            sa.select(Question).where(Question.question_id == payload.question_id)
        )
    ).scalar_one_or_none()
    if question is None:
        raise ApiError(
            "question_not_found",
            f"question {payload.question_id} does not exist",
            status.HTTP_404_NOT_FOUND,
            "question_id",
        )

    # La forma se valida contra el tipo REAL de la pregunta, no contra lo que declare el cliente.
    try:
        answers.validate_shape(question.type, payload.answer)
        if question.type is QuestionType.TRAIT_MULTISELECT:
            await answers.validate_trait_codes(session, payload.answer)
    except answers.AnswerShapeError as exc:
        raise ApiError(
            "answer_shape_mismatch",
            f"answer does not match the shape expected for question type "
            f"'{question.type.value}': {exc}",
            status.HTTP_400_BAD_REQUEST,
            "answer",
        ) from exc
    except answers.UnknownTraitError as exc:
        raise ApiError(
            "unknown_trait_code",
            f"unknown or inactive trait codes: {', '.join(exc.codes)}",
            status.HTTP_400_BAD_REQUEST,
            "answer",
        ) from exc

    now = dt.datetime.now(dt.UTC)
    try:
        rate = await responses.check_rate_limit(session, current.respondent, now)
    except responses.RateLimitError as exc:
        raise ApiError(
            "rate_limit_exceeded",
            "too many responses; slow down",
            status.HTTP_429_TOO_MANY_REQUESTS,
            headers={
                "Retry-After": str(exc.retry_after),
                "X-RateLimit-Limit": str(responses.PER_MINUTE),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(now.timestamp()) + exc.retry_after),
            },
        ) from exc

    await responses.record(
        session, current.respondent, question, payload.answer, payload.response_time_ms, now
    )

    http_response.headers["X-RateLimit-Limit"] = str(rate.limit)
    http_response.headers["X-RateLimit-Remaining"] = str(rate.remaining)
    http_response.headers["X-RateLimit-Reset"] = str(rate.reset)

    return RecordedResponse(
        recorded=True,
        feedback=await responses.build_feedback(session, question, payload.answer),
        progress=responses.build_progress(
            current.respondent, await profile.agreement_rate(session, current.respondent)
        ),
    )
