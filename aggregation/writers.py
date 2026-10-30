"""Los seis CSV con el formato fijo de `docs/25-agregacion.md` §4.6 (CA-408).

**De este archivo depende el SHA-256.** Cada número sale con un formato explícito —nunca el que
elija `str(float)`—, las filas en el orden declarado, UTF-8 sin BOM, fin de línea `\\n` y comillas
sólo donde el valor las necesite. Las cabeceras son las de `docs/26-esquema-de-salida.md`, que un
test compara contra las de `docs/examples/`.
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from aggregation.estimators.simple import power_at
from aggregation.fits import (
    DimensionResult,
    DuoKey,
    DuoResult,
    Estimate,
    LaneResult,
    PeakResult,
    TraitResult,
)
from aggregation.load import ChampionInfo
from aggregation.params import RunParams

ID_COLUMNS = [
    "champion_id",
    "riot_key",
    "display_name",
    "roles",
    "pool_tier",
    "patch_window",
    "exported_at",
]

HEADERS: dict[str, list[str]] = {
    "champion_dimensions": [
        *ID_COLUMNS,
        "dimension",
        "score",
        "score_ci_low",
        "score_ci_high",
        "score_n",
        "score_support",
        "unknown_rate",
        "score_norm",
    ],
    "peak_timing": [
        *ID_COLUMNS,
        "peak_minute",
        "peak_minute_ci_low",
        "peak_minute_ci_high",
        "peak_minute_n",
        "peak_minute_support",
        "power_at_5",
        "power_at_10",
        "power_at_15",
        "power_at_20",
        "power_at_25",
    ],
    "champion_lane_strength": [
        *ID_COLUMNS,
        "role",
        "lane_strength",
        "lane_strength_ci_low",
        "lane_strength_ci_high",
        "lane_strength_n",
        "lane_strength_support",
    ],
    "champion_traits": [
        *ID_COLUMNS,
        "trait",
        "proportion",
        "proportion_ci_low",
        "proportion_ci_high",
        "proportion_n",
        "proportion_support",
    ],
    "matchup_matrix": [
        "champion_a_id",
        "champion_a_key",
        "champion_b_id",
        "champion_b_key",
        "role",
        "advantage",
        "advantage_ci_low",
        "advantage_ci_high",
        "n_responses",
        "support",
        "is_observed",
        "patch_window",
    ],
    "duo_features": [
        "champion_a_id",
        "champion_a_key",
        "champion_b_id",
        "champion_b_key",
        "role_a",
        "role_b",
        "synergy",
        "synergy_ci_low",
        "synergy_ci_high",
        "synergy_n",
        "synergy_support",
        "synergy_is_observed",
        "lane_strength",
        "lane_strength_ci_low",
        "lane_strength_ci_high",
        "lane_strength_n",
        "lane_strength_support",
        "lane_strength_is_observed",
        "patch_window",
    ],
}

#: El orden de los archivos en una corrida y en `exports`.
KINDS = list(HEADERS)

#: Los roles del 1v1, en el orden de 25 §4.6.
LANE_ROLES = ("top", "mid", "adc")
#: El orden de los roles al ordenar filas: el del enum `lane_role` del esquema.
ROLE_ORDER = {"top": 0, "jungle": 1, "mid": 2, "adc": 3, "support": 4}

POWER_MINUTES = (5, 10, 15, 20, 25)


def number(value: float | None, digits: int) -> str:
    """El `%.Nf` de §4.6, y vacío —no cero— cuando no hay valor (§4.5)."""
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def integer(value: float | None) -> str:
    return "" if value is None else str(int(value))


def boolean(value: bool) -> str:
    return "true" if value else "false"


@dataclass(frozen=True, slots=True)
class Written:
    kind: str
    file_name: str
    sha256: str
    rows: int
    columns: int
    path: Path


def _identification(champion: ChampionInfo, params: RunParams) -> list[str]:
    return [
        str(champion.champion_id),
        champion.riot_key,
        champion.display_name,
        "|".join(champion.roles),
        str(champion.pool_tier),
        params.patch_window,
        params.exported_at.isoformat(),
    ]


def _block(estimate: Estimate, digits: int) -> list[str]:
    return [
        number(estimate.value, digits),
        number(estimate.low, digits),
        number(estimate.high, digits),
        str(estimate.n),
        estimate.support,
    ]


def dimension_rows(
    results: Sequence[DimensionResult],
    pool: Sequence[int],
    champions: dict[int, ChampionInfo],
    params: RunParams,
) -> list[list[str]]:
    rows = []
    for c in pool:
        for result in results:
            estimate = result.estimates[c]
            rows.append(
                [
                    *_identification(champions[c], params),
                    result.code,
                    *_block(estimate, 3),
                    number(result.unknown_rate.get(c), 2),
                    number(result.norm.get(c), 3),
                ]
            )
    return rows


def peak_rows(
    result: PeakResult,
    pool: Sequence[int],
    champions: dict[int, ChampionInfo],
    params: RunParams,
) -> list[list[str]]:
    rows = []
    for c in pool:
        e = result.estimates[c]
        peak = None if e.value is None else int(e.value)
        powers = [
            "" if peak is None else number(power_at(t, peak, params.sigma), 2)
            for t in POWER_MINUTES
        ]
        rows.append(
            [
                *_identification(champions[c], params),
                integer(e.value),
                integer(e.low),
                integer(e.high),
                str(e.n),
                e.support,
                *powers,
            ]
        )
    return rows


def lane_rows(
    results: dict[str, LaneResult],
    pool: Sequence[int],
    champions: dict[int, ChampionInfo],
    params: RunParams,
) -> list[list[str]]:
    rows = []
    for c in pool:
        for role in LANE_ROLES:
            estimate = results[role].estimates.get(c, Estimate.empty())
            rows.append([*_identification(champions[c], params), role, *_block(estimate, 3)])
    return rows


def trait_rows(
    result: TraitResult,
    traits: Sequence[str],
    pool: Sequence[int],
    champions: dict[int, ChampionInfo],
    params: RunParams,
) -> list[list[str]]:
    return [
        [*_identification(champions[c], params), trait, *_block(result.estimates[(c, trait)], 3)]
        for c in pool
        for trait in traits
    ]


def matchup_rows(
    results: dict[str, LaneResult], champions: dict[int, ChampionInfo], params: RunParams
) -> list[list[str]]:
    rows = []
    for role in LANE_ROLES:
        for m in sorted(results[role].matchups, key=lambda m: (m.a, m.b)):
            e = m.advantage
            rows.append(
                [
                    str(m.a),
                    champions[m.a].riot_key,
                    str(m.b),
                    champions[m.b].riot_key,
                    role,
                    number(e.value, 3),
                    number(e.low, 3),
                    number(e.high, 3),
                    str(e.n),
                    e.support,
                    boolean(m.observed),
                    params.patch_window,
                ]
            )
    return rows


def duo_rows(
    synergy: Iterable[DuoResult],
    lane: DuoResult | None,
    champions: dict[int, ChampionInfo],
    params: RunParams,
) -> list[list[str]]:
    """Una fila por dupla. En las de bot, la unión de los dos modelos (§8.2, nota del 29/10)."""
    keys: set[DuoKey] = set()
    by_model: list[DuoResult] = [*synergy, *([lane] if lane is not None else [])]
    for result in by_model:
        keys |= set(result.rows)
    synergy_rows = {k: v for result in synergy for k, v in result.rows.items()}
    lane_rows_ = lane.rows if lane is not None else {}

    def order(key: DuoKey) -> tuple[int, int, int, int]:
        (a, role_a), (b, role_b) = key
        return ROLE_ORDER[role_a], ROLE_ORDER[role_b], a, b

    rows = []
    for key in sorted(keys, key=order):
        (a, role_a), (b, role_b) = key
        cells = [str(a), champions[a].riot_key, str(b), champions[b].riot_key, role_a, role_b]
        for source in (synergy_rows, lane_rows_):
            duo = source.get(key)
            if duo is None:
                cells += [*_block(Estimate.empty(), 3), boolean(False)]
            else:
                cells += [*_block(duo.estimate, 3), boolean(duo.observed)]
        cells.append(params.patch_window)
        rows.append(cells)
    return rows


def write(kind: str, rows: list[list[str]], patch: str, out: Path) -> Written:
    """Escribe un archivo y devuelve su SHA-256, calculado sobre los bytes escritos."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(HEADERS[kind])
    writer.writerows(rows)
    data = buffer.getvalue().encode("utf-8")
    name = f"{kind}_v{patch}.csv"
    path = out / name
    path.write_bytes(data)
    return Written(
        kind=kind,
        file_name=name,
        sha256=hashlib.sha256(data).hexdigest(),
        rows=len(rows),
        columns=len(HEADERS[kind]),
        path=path,
    )
