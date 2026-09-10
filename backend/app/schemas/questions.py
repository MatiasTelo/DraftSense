"""Contrato de `GET /questions/next` (`docs/12-api.md` §2.3).

La pregunta es una **unión discriminada por `type`**. Toda opción que representa una entidad
comparable lleva un arreglo `champions`, tenga uno o dos elementos, para que el cliente renderice
duplas y campeones sueltos con el mismo componente (§1.2). No lo "optimices" mandando un objeto
suelto cuando hay un solo campeón.

En la semana 2 sólo existe `pairwise_dimension`; los otros cuatro tipos entran en las semanas 3,
4 y 8 según `docs/20-tipos-de-pregunta.md` §8.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


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
    label: str | None = None
    champions: list[ChampionRef]


class PairwiseDimensionQuestion(BaseModel):
    question_id: int
    type: Literal["pairwise_dimension"] = "pairwise_dimension"
    prompt: str
    help: Help | None
    options: list[Side]


class QuestionBatch(BaseModel):
    questions: list[PairwiseDimensionQuestion]
