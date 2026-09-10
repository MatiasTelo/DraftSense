"""`GET /me` y `GET /leaderboard` (`docs/12-api.md` §2.5 y §2.6)."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.dependencies import CurrentSessionDep, SessionDep
from app.errors import ApiError
from app.schemas.profile import LeaderboardOut, MeOut
from app.services import leaderboard, profile

router = APIRouter(tags=["profile"])


@router.get("/me", response_model=MeOut)
async def me(session: SessionDep, current: CurrentSessionDep) -> MeOut:
    """Perfil y progreso.

    `trust_score` no aparece, ni el resultado de los honeypots, ni cuáles preguntas lo eran, ni
    ninguna métrica de la que se pueda despejar alguna de esas cosas (RF-207, CA-303).
    """
    respondent = current.respondent
    return MeOut(
        answers_count=respondent.answers_count,
        current_streak=respondent.current_streak,
        best_streak=respondent.best_streak,
        current_day_streak=respondent.current_day_streak,
        best_day_streak=respondent.best_day_streak,
        agreement_rate=await profile.agreement_rate(session, respondent),
        coverage=await profile.coverage(session, respondent),
        rank_percentile=await profile.rank_percentile(session, respondent),
        alias=respondent.alias,
    )


@router.get("/leaderboard", response_model=LeaderboardOut)
async def get_leaderboard(
    session: SessionDep,
    current: CurrentSessionDep,
    window: Annotated[str, Query()] = "week",
) -> LeaderboardOut:
    """Top 50 por cantidad de respuestas, en la ventana pedida."""
    if window not in leaderboard.WINDOWS:
        raise ApiError(
            "invalid_parameter",
            f"window must be one of {list(leaderboard.WINDOWS)}",
            status.HTTP_400_BAD_REQUEST,
            "window",
        )
    return await leaderboard.build(
        session, window, current.respondent, dt.datetime.now(dt.UTC)
    )
