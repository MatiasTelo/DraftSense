"""Qué entra a una corrida y con qué peso (`docs/25-agregacion.md` §1 y §2).

La consulta base es la de §1.1, con los cinco filtros de §1.2: ventana de parches resuelta por
`released_at` —no comparando versiones como texto, donde `'16.9' > '16.20'`—, sin retests, sin
honeypots, sin respondedores marcados y con `trust_score ≥ min_trust`. **El `ORDER BY response_id`
es parte del contrato**: el bootstrap consume esta lista en orden, y otro orden daría otro archivo
con los mismos datos (CA-408).
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from aggregation.params import RunParams
from app.models import (
    Champion,
    Dimension,
    Patch,
    Question,
    QuestionType,
    Respondent,
    Response,
    Trait,
)
from app.services import app_settings


class NoDataError(Exception):
    """Ninguna respuesta pasó los filtros: la corrida falla y no escribe nada (§7)."""


@dataclass(frozen=True, slots=True)
class Row:
    response_id: int
    respondent_id: uuid.UUID
    patch_id: int
    type: QuestionType
    answer: dict[str, Any]
    #: `trust · 0.5 ^ (días / H)` (§2.1). La única ponderación del pipeline.
    weight: float
    champion_a: int
    champion_b: int | None
    champion_c: int | None
    champion_d: int | None
    dimension_id: int | None
    role: str | None
    duo_ctx: str | None
    role_a: str | None
    role_b: str | None
    role_c: str | None
    role_d: str | None


@dataclass(frozen=True, slots=True)
class ChampionInfo:
    champion_id: int
    riot_key: str
    display_name: str
    roles: tuple[str, ...]
    pool_tier: int


@dataclass(frozen=True, slots=True)
class Dataset:
    rows: list[Row]
    champions: dict[int, ChampionInfo]
    #: El pool del export: activos con `pool_tier ≤ sampler.enabled_pool_tiers` (§8.2, nota del
    #: 29/10). Son los que tienen filas en los archivos por campeón, en orden de id.
    pool: list[int]
    #: Las dimensiones activas, `(dimension_id, code)`, en el orden de 26 §3.2.
    dimensions: list[tuple[int, str]]
    #: Los atributos activos, en el orden de 26 §3.5.
    traits: list[str]
    #: El último parche de la ventana: el `<patch>` de los nombres de archivo y `exports.patch_id`.
    patch_id: int
    patch_version: str


def weight(trust: float, created_at: dt.datetime, params: RunParams) -> float:
    """§2.1. Los días son enteros: la fecha de la respuesta en UTC contra `exported_at`."""
    created = created_at.astimezone(dt.UTC).date()
    days = (params.exported_at - created).days
    return float(trust) * float(0.5 ** (days / params.halflife))


async def _window(session: AsyncSession, params: RunParams) -> list[Patch]:
    bounds = []
    for version in (params.patch_from, params.patch_to):
        patch = (
            await session.execute(sa.select(Patch).where(Patch.version == version))
        ).scalar_one_or_none()
        if patch is None:
            raise ValueError(f"el parche {version} no existe")
        bounds.append(patch.released_at)
    low, high = bounds
    if low > high:
        raise ValueError(f"ventana invertida: {params.patch_window}")
    return list(
        (
            await session.execute(
                sa.select(Patch)
                .where(Patch.released_at.between(low, high))
                .order_by(Patch.released_at, Patch.patch_id)
            )
        ).scalars()
    )


async def load(session: AsyncSession, params: RunParams) -> Dataset:
    """§8.2, paso 2: el conjunto filtrado y el peso de cada fila."""
    patches = await _window(session, params)
    patch_ids = [p.patch_id for p in patches]
    last = next(p for p in patches if p.version == params.patch_to)

    statement = (
        sa.select(Response, Question, Respondent.trust_score)
        .join(Question, Question.question_id == Response.question_id)
        .join(Respondent, Respondent.respondent_id == Response.respondent_id)
        .where(
            Response.patch_id.in_(patch_ids),
            Response.is_retest_of.is_(None),
            ~Question.is_honeypot,
            ~Respondent.is_flagged,
            Respondent.trust_score >= params.min_trust,
        )
        .order_by(Response.response_id)
    )
    rows: list[Row] = []
    for response, question, trust in (await session.execute(statement)).tuples():
        rows.append(
            Row(
                response_id=response.response_id,
                respondent_id=response.respondent_id,
                patch_id=response.patch_id,
                type=QuestionType(response.type),
                answer=response.answer,
                weight=weight(float(trust), response.created_at, params),
                champion_a=question.champion_a,
                champion_b=question.champion_b,
                champion_c=question.champion_c,
                champion_d=question.champion_d,
                dimension_id=question.dimension_id,
                role=_text(question.role),
                duo_ctx=_text(question.duo_ctx),
                role_a=_text(question.role_a),
                role_b=_text(question.role_b),
                role_c=_text(question.role_c),
                role_d=_text(question.role_d),
            )
        )
    if not rows:
        raise NoDataError(
            f"ninguna respuesta de {params.patch_window} pasa los filtros "
            f"(min_trust {params.min_trust:.3f})"
        )

    champions = {
        c.champion_id: ChampionInfo(
            champion_id=c.champion_id,
            riot_key=c.riot_key,
            display_name=c.display_name,
            roles=tuple(str(r) for r in c.roles),
            pool_tier=c.pool_tier,
        )
        for c in (await session.execute(sa.select(Champion))).scalars()
    }
    tiers = int(await app_settings.get(session, "sampler.enabled_pool_tiers", 1))
    pool = sorted(
        (
            await session.execute(
                sa.select(Champion.champion_id).where(
                    Champion.is_active, Champion.pool_tier <= tiers
                )
            )
        ).scalars()
    )
    dimensions = [
        (d.dimension_id, d.code)
        for d in (
            await session.execute(
                sa.select(Dimension)
                .where(Dimension.is_active)
                .order_by(Dimension.display_order, Dimension.dimension_id)
            )
        ).scalars()
    ]
    traits = list(
        (
            await session.execute(
                sa.select(Trait.code)
                .where(Trait.is_active)
                .order_by(Trait.display_order, Trait.trait_id)
            )
        ).scalars()
    )
    return Dataset(
        rows=rows,
        champions=champions,
        pool=pool,
        dimensions=dimensions,
        traits=traits,
        patch_id=last.patch_id,
        patch_version=last.version,
    )


def _text(value: object) -> str | None:
    return None if value is None else str(value)
