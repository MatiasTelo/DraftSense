"""Contrato de `GET /questions/next` (`docs/12-api.md` §2.3).

La pregunta es una **unión discriminada por `type`**. Toda opción que representa una entidad
comparable lleva un arreglo `champions`, tenga uno o dos elementos, para que el cliente renderice
duplas y campeones sueltos con el mismo componente (§1.2). No lo "optimices" mandando un objeto
suelto cuando hay un solo campeón.

Desde la semana 4 existen el tipo 1, el tipo 2 y la variante 1v1 del tipo 3. Desde el 08/10 el
tipo 1 es un ranking de cinco campeones (ADR-022). Desde la semana 8, la variante 2v2, el tipo 4 y
el tipo 5 (`docs/20-tipos-de-pregunta.md` §8).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models import DuoContext, LaneRole
from app.schemas.common import is_absent


class ChampionRef(BaseModel):
    id: int
    key: str
    name: str
    image_url: str


class Help(BaseModel):
    label: str
    text: str


class Side(BaseModel):
    key: str
    #: Sólo la llevan las opciones sin campeones, como `unknown`: un lado que ya muestra un
    #: campeón no necesita etiqueta y el contrato no la incluye.
    label: str | None = Field(default=None, exclude_if=is_absent)
    champions: list[ChampionRef]


class PairwiseDimensionQuestion(BaseModel):
    """Tipo 1: cinco campeones para ordenar en una dimensión (ADR-022).

    `question_id` es el del par ancla, que es lo que el cliente manda en `queued`. Nada dice cuál
    de los cinco forma el ancla: los campeones llegan en orden aleatorio.
    """

    question_id: int
    ranking_id: int
    type: Literal["pairwise_dimension"] = "pairwise_dimension"
    prompt: str
    instruction: str
    help: Help | None
    champions: list[ChampionRef]
    unknown_label: str


class Subject(BaseModel):
    """El campeón sobre el que se pregunta. Es un arreglo por la misma razón que `Side`."""

    champions: list[ChampionRef]


class SliderMark(BaseModel):
    at: int
    label: str


class Slider(BaseModel):
    min: int
    max: int
    step: int
    default: int
    unit: str
    marks: list[SliderMark]


class PeakTimingQuestion(BaseModel):
    question_id: int
    type: Literal["peak_timing"] = "peak_timing"
    prompt: str
    help: Help | None
    subject: Subject
    slider: Slider


class LaneContext(BaseModel):
    """Dónde ocurre el enfrentamiento: `role` en el 1v1, `duo_context` en el 2v2 de bot.

    Cada variante lleva sólo su clave (`docs/12-api.md` §2.3).
    """

    role: LaneRole | None = Field(default=None, exclude_if=is_absent)
    duo_context: DuoContext | None = Field(default=None, exclude_if=is_absent)
    label: str


class DuoContextOut(BaseModel):
    """El contexto de una pregunta de tipo 4."""

    duo_context: DuoContext
    label: str


class Option(BaseModel):
    key: str
    label: str


class LaneMatchupQuestion(BaseModel):
    question_id: int
    type: Literal["lane_matchup"] = "lane_matchup"
    prompt: str
    help: Help | None
    context: LaneContext
    sides: list[Side]
    options: list[Option]


class DuoSynergyQuestion(BaseModel):
    """Tipo 4. Los lados son `pair_1` (arriba) y `pair_2` (abajo), cada uno con sus dos campeones
    en el orden de roles del contexto (ADR-026)."""

    question_id: int
    type: Literal["duo_synergy"] = "duo_synergy"
    prompt: str
    help: Help | None
    context: DuoContextOut
    sides: list[Side]
    options: list[Option]


class TraitOption(BaseModel):
    code: str
    label: str
    help: str


class TraitMultiselectQuestion(BaseModel):
    """Tipo 5. `help` de la pregunta es `null`: cada atributo trae su propia definición."""

    question_id: int
    type: Literal["trait_multiselect"] = "trait_multiselect"
    prompt: str
    subtitle: str
    help: Help | None
    subject: Subject
    traits: list[TraitOption]


#: No se llama `Question` para no chocar con el modelo ORM, que se importa en los mismos módulos.
QuestionOut = Annotated[
    PairwiseDimensionQuestion
    | PeakTimingQuestion
    | LaneMatchupQuestion
    | DuoSynergyQuestion
    | TraitMultiselectQuestion,
    Field(discriminator="type"),
]


class QuestionBatch(BaseModel):
    questions: list[QuestionOut]
