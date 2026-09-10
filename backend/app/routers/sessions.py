"""`POST /sessions` y `POST /sessions/onboarding` (`docs/12-api.md` §2.1 y §2.2)."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.dependencies import CurrentSessionDep, SessionDep, set_session_cookie
from app.errors import ApiError
from app.models import Respondent
from app.schemas.sessions import OnboardingIn, OnboardingOut, SessionOut
from app.services import sessions

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _to_out(respondent: Respondent) -> SessionOut:
    return SessionOut(
        respondent_id=str(respondent.respondent_id),
        onboarding_seen=respondent.onboarding_seen,
        answers_count=respondent.answers_count,
        current_streak=respondent.current_streak,
        best_streak=respondent.best_streak,
        current_day_streak=respondent.current_day_streak,
        best_day_streak=respondent.best_day_streak,
    )


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    response: Response, session: SessionDep, current: CurrentSessionDep
) -> SessionOut:
    """Crea la sesión anónima, o la revalida si ya existía.

    **Es idempotente** (CA-002): con una cookie válida no crea una identidad nueva, devuelve el
    mismo `respondent_id` y sólo actualiza `last_seen`. En ese caso responde `200` en vez de `201`.
    """
    if not current.created:
        await sessions.touch(session, current.respondent)
        response.status_code = status.HTTP_200_OK
    return _to_out(current.respondent)


@router.post("/onboarding", response_model=OnboardingOut)
async def save_onboarding(
    payload: OnboardingIn, session: SessionDep, current: CurrentSessionDep
) -> OnboardingOut:
    """Guarda rango, rol y horas declaradas. Los tres pueden ser nulos.

    Omitir el onboarding **es** una respuesta: el cliente llama con los tres campos en `null` y
    `onboarding_seen` queda igual en `true`, para no volver a preguntar (CA-005).
    """
    try:
        rank = payload.validated_rank()
        hours = payload.validated_hours()
    except ValueError as exc:
        raise ApiError(
            "invalid_parameter", str(exc), status.HTTP_400_BAD_REQUEST, "declared_rank"
        ) from exc

    await sessions.save_onboarding(
        session,
        current.respondent,
        declared_rank=rank,
        declared_main_role=payload.declared_main_role,
        declared_hours_bucket=hours,
    )
    return OnboardingOut(onboarding_seen=True)


__all__ = ["router", "set_session_cookie"]
