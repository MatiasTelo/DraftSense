"""Tipos enumerados del esquema.

Los valores son exactamente los del DDL de `docs/11-modelo-de-datos.md`. Se declaran como
`StrEnum` para que el valor que viaja a Postgres y el que serializa Pydantic sean el mismo.
"""

from __future__ import annotations

import enum
from enum import StrEnum

import sqlalchemy as sa


class QuestionType(StrEnum):
    """Los cinco tipos de pregunta.

    `LANE_MATCHUP` cubre dos variantes —el 1v1 de línea y el 2v2 de bot— porque comparten
    enunciado, escala de cinco niveles y modelo de agregación: lo único que cambia es si el
    competidor es un campeón o una dupla. Ver `docs/20-tipos-de-pregunta.md` §4.
    """

    PAIRWISE_DIMENSION = "pairwise_dimension"
    PEAK_TIMING = "peak_timing"
    LANE_MATCHUP = "lane_matchup"
    DUO_SYNERGY = "duo_synergy"
    TRAIT_MULTISELECT = "trait_multiselect"


class AggregateScope(StrEnum):
    """Granularidad de una fila de `aggregates`."""

    CHAMPION_DIMENSION = "champion_dimension"
    CHAMPION_PEAK = "champion_peak"
    MATCHUP_PAIR = "matchup_pair"
    DUO_SYNERGY = "duo_synergy"
    DUO_LANE_STRENGTH = "duo_lane_strength"
    CHAMPION_TRAIT = "champion_trait"


class SupportLevel(StrEnum):
    """Juicio sobre el soporte muestral de una estimación.

    Nada se excluye del CSV por soporte bajo: se marca. Ver ADR-011.
    """

    SOLID = "solid"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"


class LaneRole(StrEnum):
    """Roles individuales: los que ocupa un campeón."""

    TOP = "top"
    JUNGLE = "jungle"
    MID = "mid"
    ADC = "adc"
    SUPPORT = "support"


class DuoContext(StrEnum):
    """Contextos de dupla: dónde dos campeones actúan juntos.

    Es un enum aparte y no un valor más de `LaneRole` porque 'bot' no es un rol que ocupe un
    campeón, sino una pareja de roles (adc + support).
    """

    BOT = "bot"
    TOP_JUNGLE = "top_jungle"
    MID_JUNGLE = "mid_jungle"


def pg_enum(py_enum: type[enum.Enum], name: str) -> sa.Enum:
    """Construye el tipo ENUM de Postgres a partir de un enum de Python.

    `values_callable` es imprescindible: sin él SQLAlchemy usaría los *nombres* de los miembros
    ('PAIRWISE_DIMENSION') en vez de sus valores ('pairwise_dimension'), y el tipo creado en la
    base no coincidiría con el DDL documentado.
    """
    return sa.Enum(
        py_enum,
        name=name,
        native_enum=True,
        create_type=False,
        values_callable=lambda members: [m.value for m in members],
    )


QUESTION_TYPE = pg_enum(QuestionType, "question_type")
AGGREGATE_SCOPE = pg_enum(AggregateScope, "aggregate_scope")
SUPPORT_LEVEL = pg_enum(SupportLevel, "support_level")
LANE_ROLE = pg_enum(LaneRole, "lane_role")
DUO_CONTEXT = pg_enum(DuoContext, "duo_context")

#: Todos los tipos ENUM del esquema, en el orden en que la migración inicial debe crearlos.
ALL_ENUMS: tuple[tuple[type[enum.Enum], str], ...] = (
    (QuestionType, "question_type"),
    (AggregateScope, "aggregate_scope"),
    (SupportLevel, "support_level"),
    (LaneRole, "lane_role"),
    (DuoContext, "duo_context"),
)
