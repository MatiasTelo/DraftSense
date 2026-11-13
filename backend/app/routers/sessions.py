"""`POST /sessions` y `POST /sessions/onboarding` (`docs/12-api.md` §2.1 y §2.2)."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Response, status

from app.dependencies import CurrentSessionDep, SessionDep, set_session_cookie
from app.errors import ApiError
from app.models import Respondent
from app.schemas.sessions import OnboardingIn, OnboardingOut, SessionOut
from app.services import sessions, streaks

router = APIRouter(prefix="/sessions", tags=["sessions"])


async def _to_out(session: SessionDep, respondent: Respondent) -> SessionOut:
    current_streak, current_day_streak = await streaks.visible(
        session, respondent, dt.datetime.now(dt.UTC)
    )
    return SessionOut(
        respondent_id=str(respondent.respondent_id),
        onboarding_seen=respondent.onboarding_seen,
        answers_count=respondent.answers_count,
        current_streak=current_streak,
        best_streak=respondent.best_streak,
        current_day_streak=current_day_streak,
        best_day_streak=respondent.best_day_streak,
    )


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    response: Response, session: SessionDep, current: CurrentSessionDep
) -> SessionOut:
    """Crea la sesión anónima, o la revalida si ya existía.

    **Es idempotente** (CA-002): con una cookie válida no crea una identidad nueva, devuelve el
    mismo `respondent_id`. En ese caso responde `200` en vez de `201`.

    **No toca `last_seen`.** La racha de respuestas se corta comparando `now() - last_seen` contra
    los 30 minutos (`docs/23-gamificacion.md` §2.1) y la SPA llama acá en cada carga: si esto lo
    actualizara, quien vuelve al día siguiente tendría una pausa de segundos y la racha no se
    cortaría nunca. `last_seen` lo escribe sólo `POST /responses`.
    """
    if not current.created:
        response.status_code = status.HTTP_200_OK
    return await _to_out(session, current.respondent)


@router.post("/onboarding", response_model=OnboardingOut)
async def save_onboarding(
    payload: OnboardingIn, session: SessionDep, current: CurrentSessionDep
) -> OnboardingOut:
    """Guarda rango, rol y horas declaradas. Los tres pueden ser nulos.

    Omitir el onboarding **es** una respuesta: el cliente llama con los tres campos en `null` y
    `onboarding_seen` queda igual en `true`, para no volver a preguntar (CA-005).
    """
    # Una validación por campo: con un solo `except` el error señalaba siempre `declared_rank`,
    # también cuando lo inválido eran las horas.
    try:
        rank = payload.validated_rank()
    except ValueError as exc:
        raise ApiError(
            "invalid_parameter", str(exc), status.HTTP_400_BAD_REQUEST, "declared_rank"
        ) from exc
    try:
        hours = payload.validated_hours()
    except ValueError as exc:
        raise ApiError(
            "invalid_parameter", str(exc), status.HTTP_400_BAD_REQUEST, "declared_hours_bucket"
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
