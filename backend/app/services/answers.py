"""Validación de la forma del `answer` contra el tipo real de la pregunta (RF-108).

Las formas son las de `docs/11-modelo-de-datos.md` §5. La restricción `responses_answer_shape`
las repite en la base y **esa es la que manda**: acá se validan antes para poder devolver un 400
con el código del contrato en vez de un 500 por violación de CHECK, y para agregar lo que SQL no
expresa cómodamente —que `minute` sea entero y que cada código de `traits` exista y esté activo—.

Que la validación esté en los dos lados no es duplicación ociosa: `responses` es append-only, así
que un dato mal formado no se puede corregir después (ADR-002, CA-203).
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuestionType, Trait

PAIRWISE_CHOICES = ("a", "b", "unknown")
LANE_MATCHUP_CHOICES = ("a_strong", "a_slight", "even", "b_slight", "b_strong")
DUO_SYNERGY_CHOICES = ("pair_1", "pair_2", "similar")

PEAK_MIN_MINUTE = 0
PEAK_MAX_MINUTE = 40


class AnswerShapeError(Exception):
    """El `answer` no corresponde al tipo de la pregunta."""


class UnknownTraitError(Exception):
    """Un código de `traits` no existe o está inactivo."""

    def __init__(self, codes: list[str]) -> None:
        super().__init__(", ".join(codes))
        self.codes = codes


def _only_key(answer: dict[str, Any], key: str) -> Any:
    if set(answer) != {key}:
        raise AnswerShapeError(f"answer must have exactly the key '{key}'")
    return answer[key]


def _choice(answer: dict[str, Any], valid: tuple[str, ...]) -> None:
    value = _only_key(answer, "choice")
    if value not in valid:
        raise AnswerShapeError(f"choice must be one of {list(valid)}")


def validate_shape(question_type: QuestionType, answer: dict[str, Any]) -> None:
    """Valida la forma. Lanza `AnswerShapeError` si no corresponde."""
    match question_type:
        case QuestionType.PAIRWISE_DIMENSION:
            _choice(answer, PAIRWISE_CHOICES)
        case QuestionType.LANE_MATCHUP:
            _choice(answer, LANE_MATCHUP_CHOICES)
        case QuestionType.DUO_SYNERGY:
            _choice(answer, DUO_SYNERGY_CHOICES)
        case QuestionType.PEAK_TIMING:
            minute = _only_key(answer, "minute")
            # `bool` es subclase de `int` en Python: sin este descarte, `{"minute": true}`
            # pasaría como el minuto 1.
            if isinstance(minute, bool) or not isinstance(minute, int):
                raise AnswerShapeError("minute must be an integer")
            if not PEAK_MIN_MINUTE <= minute <= PEAK_MAX_MINUTE:
                raise AnswerShapeError(
                    f"minute must be between {PEAK_MIN_MINUTE} and {PEAK_MAX_MINUTE}"
                )
        case QuestionType.TRAIT_MULTISELECT:
            traits = _only_key(answer, "traits")
            if not isinstance(traits, list) or not all(isinstance(t, str) for t in traits):
                raise AnswerShapeError("traits must be an array of strings")
            if len(set(traits)) != len(traits):
                raise AnswerShapeError("traits must not repeat")


async def validate_trait_codes(session: AsyncSession, answer: dict[str, Any]) -> None:
    """Que cada código exista y esté activo. La lista vacía es válida: significa 'ninguno'."""
    codes: list[str] = answer.get("traits", [])
    if not codes:
        return
    known = set(
        (
            await session.execute(
                sa.select(Trait.code).where(Trait.code.in_(codes), Trait.is_active)
            )
        )
        .scalars()
        .all()
    )
    unknown = [c for c in codes if c not in known]
    if unknown:
        raise UnknownTraitError(unknown)
