"""Una corrida completa: los ocho pasos de `docs/25-agregacion.md` §8.2.

Lo usan la línea de comandos (`run.py`) y el panel de administración, que la lanza en segundo
plano. Ninguno de los dos tiene lógica propia: si algo cambia en cómo se corre, cambia acá.

**La partición de trabajo es parte del contrato** (§8.2, nota del 29/10): los ajustes van en un
orden fijo y cada uno recibe el generador hijo de la semilla en esa posición. Correrlos en
paralelo o en serie da los mismos números, y por eso el mismo SHA-256 (CA-408).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from aggregation import fits, record, writers
from aggregation.load import Dataset, Row, load
from aggregation.params import RunParams
from app.models import QuestionType

#: Los dos roles de cada contexto de dupla, en el orden en que se escriben (ADR-026).
DUO_CONTEXTS: dict[str, tuple[str, str]] = {
    "bot": ("adc", "support"),
    "top_jungle": ("top", "jungle"),
    "mid_jungle": ("mid", "jungle"),
}


@dataclass(frozen=True, slots=True)
class Task:
    """Un ajuste de la partición: qué función, con qué filas y con qué nombre."""

    name: str
    function: Callable[..., Any]
    args: tuple[Any, ...]
    #: Si consume el generador. Los atributos no: Wilson no remuestrea.
    random: bool = True


@dataclass(slots=True)
class RunResult:
    params: RunParams
    files: list[writers.Written]
    export_ids: list[int]
    reports: list[fits.FitReport]
    responses: int
    respondents: int
    out: Path
    extra: dict[str, Any] = field(default_factory=dict)


def _select(rows: Sequence[Row], test: Callable[[Row], bool]) -> list[Row]:
    return [r for r in rows if test(r)]


def tasks(data: Dataset, params: RunParams) -> list[Task]:
    """Los ajustes en el orden fijo de la partición: las dimensiones por `display_order`, los
    roles del 1v1, el 2v2 de bot, los tres contextos de sinergia, el pico y los atributos."""
    roles = {c: info.roles for c, info in data.champions.items()}
    pool = data.pool
    rows = data.rows
    result: list[Task] = []
    for dimension_id, code in data.dimensions:
        subset = [
            r
            for r in rows
            if r.type is QuestionType.PAIRWISE_DIMENSION and r.dimension_id == dimension_id
        ]
        result.append(Task(f"dimension:{code}", fits.fit_dimension, (code, subset, pool, params)))
    for role in writers.LANE_ROLES:
        subset = [
            r
            for r in rows
            if r.type is QuestionType.LANE_MATCHUP and r.champion_c is None and r.role == role
        ]
        result.append(Task(f"lane:{role}", fits.fit_lane, (role, subset, pool, roles, params)))
    bot_lane = _select(
        rows, lambda r: r.type is QuestionType.LANE_MATCHUP and r.champion_c is not None
    )
    result.append(
        Task(
            "lane:bot",
            fits.fit_duos,
            ("bot", "lane", DUO_CONTEXTS["bot"], bot_lane, pool, roles, params),
        )
    )
    for context, context_roles in DUO_CONTEXTS.items():
        subset = [r for r in rows if r.type is QuestionType.DUO_SYNERGY and r.duo_ctx == context]
        result.append(
            Task(
                f"synergy:{context}",
                fits.fit_duos,
                (context, "synergy", context_roles, subset, pool, roles, params),
            )
        )
    peaks = _select(rows, lambda r: r.type is QuestionType.PEAK_TIMING)
    result.append(Task("peak", fits.fit_peaks, (peaks, pool, params)))
    traits = _select(rows, lambda r: r.type is QuestionType.TRAIT_MULTISELECT)
    result.append(
        Task("traits", fits.fit_traits, (traits, pool, data.traits, params), random=False)
    )
    return result


def _execute(task: Task, seed: np.random.SeedSequence) -> Any:
    if task.random:
        return task.function(*task.args, np.random.default_rng(seed))
    return task.function(*task.args)


def execute(planned: Sequence[Task], seed: int, workers: int | None = None) -> list[Any]:
    """Los ajustes, en paralelo si hay más de un worker. Cada uno con su hijo de la semilla."""
    children = np.random.SeedSequence(seed).spawn(len(planned))
    count = workers if workers is not None else min(len(planned), os.cpu_count() or 1)
    if count <= 1:
        return [_execute(task, child) for task, child in zip(planned, children, strict=True)]
    with ProcessPoolExecutor(max_workers=count) as pool:
        return list(pool.map(_execute, planned, children))


def _counts(rows: Sequence[Row]) -> tuple[int, int]:
    return len(rows), len({r.respondent_id for r in rows})


async def run(
    session: AsyncSession,
    params: RunParams,
    out: Path,
    *,
    workers: int | None = None,
) -> RunResult:
    """§8.2 completo. Si ninguna respuesta pasa los filtros, `load` falla antes de escribir nada."""
    data = await load(session, params)
    planned = tasks(data, params)
    # El cómputo es CPU puro: corre fuera del event loop para no bloquear al panel.
    results = await asyncio.to_thread(execute, planned, params.seed, workers)
    by_name = {task.name: result for task, result in zip(planned, results, strict=True)}

    dimensions = [by_name[f"dimension:{code}"] for _, code in data.dimensions]
    lanes = {role: by_name[f"lane:{role}"] for role in writers.LANE_ROLES}
    synergy = [by_name[f"synergy:{context}"] for context in DUO_CONTEXTS]
    bot_lane = by_name["lane:bot"]
    peak = by_name["peak"]
    traits = by_name["traits"]

    pool, champions = data.pool, data.champions
    content = {
        "champion_dimensions": writers.dimension_rows(dimensions, pool, champions, params),
        "peak_timing": writers.peak_rows(peak, pool, champions, params),
        "champion_lane_strength": writers.lane_rows(lanes, pool, champions, params),
        "champion_traits": writers.trait_rows(traits, data.traits, pool, champions, params),
        "matchup_matrix": writers.matchup_rows(lanes, champions, params),
        "duo_features": writers.duo_rows(synergy, bot_lane, champions, params),
    }
    out.mkdir(parents=True, exist_ok=True)
    written = [
        writers.write(kind, content[kind], data.patch_version, out) for kind in writers.KINDS
    ]

    # Qué respuestas sostienen cada archivo, para `responses_included` y `respondents_included`.
    sources = {
        "champion_dimensions": [QuestionType.PAIRWISE_DIMENSION],
        "peak_timing": [QuestionType.PEAK_TIMING],
        "champion_lane_strength": [QuestionType.LANE_MATCHUP],
        "champion_traits": [QuestionType.TRAIT_MULTISELECT],
        "matchup_matrix": [QuestionType.LANE_MATCHUP],
        "duo_features": [QuestionType.DUO_SYNERGY, QuestionType.LANE_MATCHUP],
    }
    one_v_one = {"champion_lane_strength", "matchup_matrix"}
    included = {}
    for kind, kinds in sources.items():
        rows = [r for r in data.rows if r.type in kinds]
        if kind in one_v_one:
            rows = [r for r in rows if r.champion_c is None]
        elif kind == "duo_features":
            rows = [r for r in rows if r.champion_c is not None]
        included[kind] = _counts(rows)

    export_ids = await record.insert(session, data, params, written, included)

    reports = [result.report for result in results]
    responses, respondents = _counts(data.rows)
    return RunResult(
        params=params,
        files=written,
        export_ids=export_ids,
        reports=reports,
        responses=responses,
        respondents=respondents,
        out=out,
    )
