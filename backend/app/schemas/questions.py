"""Contrato de `GET /questions/next` (`docs/12-api.md` §2.3).

La pregunta es una **unión discriminada por `type`**. Toda opción que representa una entidad
comparable lleva un arreglo `champions`, tenga uno o dos elementos, para que el cliente renderice
duplas y campeones sueltos con el mismo componente (§1.2). No lo "optimices" mandando un objeto
suelto cuando hay un solo campeón.

Desde la semana 4 existen el tipo 1, el tipo 2 y la variante 1v1 del tipo 3. La variante 2v2, el
tipo 4 y el tipo 5 entran en la semana 8 (`docs/20-tipos-de-pregunta.md` §8).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models import LaneRole
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
    question_id: int
    type: Literal["pairwise_dimension"] = "pairwise_dimension"
    prompt: str
    help: Help | None
    options: list[Side]


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
    """Dónde ocurre el enfrentamiento. La variante 2v2 de la semana 8 suma `duo_context`."""

    role: LaneRole
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


#: No se llama `Question` para no chocar con el modelo ORM, que se importa en los mismos módulos.
QuestionOut = Annotated[
    PairwiseDimensionQuestion | PeakTimingQuestion | LaneMatchupQuestion,
    Field(discriminator="type"),
]


class QuestionBatch(BaseModel):
    questions: list[QuestionOut]
