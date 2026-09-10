"""Contrato de `POST /sessions` y `POST /sessions/onboarding` (`docs/12-api.md` §2.1 y §2.2)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models import LaneRole
from app.models.collection import VALID_HOURS_BUCKETS, VALID_RANKS


class SessionOut(BaseModel):
    respondent_id: str
    onboarding_seen: bool
    answers_count: int
    current_streak: int
    best_streak: int
    current_day_streak: int
    best_day_streak: int


class OnboardingIn(BaseModel):
    """Los tres campos son opcionales: `null` significa que prefirió no decir.

    Se validan contra las mismas listas que los CHECK de la tabla, para que un valor inválido
    devuelva un 422 con el campo señalado en vez de un 500 por violación de restricción.
    """

    declared_rank: str | None = Field(default=None)
    declared_main_role: LaneRole | None = Field(default=None)
    declared_hours_bucket: str | None = Field(default=None)

    def validated_rank(self) -> str | None:
        if self.declared_rank is not None and self.declared_rank not in VALID_RANKS:
            raise ValueError(f"declared_rank must be one of {list(VALID_RANKS)}")
        return self.declared_rank

    def validated_hours(self) -> str | None:
        if (
            self.declared_hours_bucket is not None
            and self.declared_hours_bucket not in VALID_HOURS_BUCKETS
        ):
            raise ValueError(f"declared_hours_bucket must be one of {list(VALID_HOURS_BUCKETS)}")
        return self.declared_hours_bucket


class OnboardingOut(BaseModel):
    onboarding_seen: bool
