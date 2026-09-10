"""Contrato de `GET /me` y `GET /leaderboard` (`docs/12-api.md` §2.5 y §2.6).

`trust_score` no aparece, ni ninguna métrica de la que se pueda despejar (RF-207, CA-303).
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class MeOut(BaseModel):
    answers_count: int
    current_streak: int
    best_streak: int
    current_day_streak: int
    best_day_streak: int
    agreement_rate: float
    coverage: dict[str, int]
    rank_percentile: float
    alias: str | None


class LeaderboardEntry(BaseModel):
    rank: int
    alias: str | None
    answers_count: int
    is_you: bool


class LeaderboardOut(BaseModel):
    window: str
    generated_at: dt.datetime
    entries: list[LeaderboardEntry]


class HealthOut(BaseModel):
    status: str
    current_patch: str | None
    db: str
