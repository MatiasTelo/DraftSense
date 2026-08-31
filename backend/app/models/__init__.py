"""Modelos SQLAlchemy del esquema de DraftSense.

Importar este paquete registra todas las tablas en `Base.metadata`, que es lo que Alembic
necesita para autogenerar y comparar migraciones.
"""

from app.models.base import Base
from app.models.catalog import (
    Champion,
    Dimension,
    Patch,
    PickRateEntry,
    PickRateSnapshot,
    Trait,
)
from app.models.collection import Question, Respondent, Response
from app.models.enums import (
    ALL_ENUMS,
    AggregateScope,
    DuoContext,
    LaneRole,
    QuestionType,
    SupportLevel,
)
from app.models.outputs import Aggregate, Export

__all__ = [
    "ALL_ENUMS",
    "Aggregate",
    "AggregateScope",
    "Base",
    "Champion",
    "Dimension",
    "DuoContext",
    "Export",
    "LaneRole",
    "Patch",
    "PickRateEntry",
    "PickRateSnapshot",
    "Question",
    "QuestionType",
    "Respondent",
    "Response",
    "SupportLevel",
    "Trait",
]
