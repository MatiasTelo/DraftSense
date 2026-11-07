"""Los ajustes de una corrida, con su bootstrap (`docs/25-agregacion.md` §4 y §5).

Cada función de acá es **un ajuste** de la partición de §8.2 —una dimensión, un rol del 1v1, un
contexto de dupla, el pico o los atributos— y recibe su propio generador, hijo de la semilla de
§4.2. Son independientes entre sí y se pueden correr en paralelo o en serie con el mismo
resultado: ninguna lee estado compartido y ninguna depende del orden en que terminen las otras.

Tres reglas del bootstrap que no son opcionales (§4.2, `references/reproducibilidad.md`):

1. **Se re-centra dentro de cada remuestreo**, igual que el ajuste completo. Sin eso, la
   indeterminación aditiva del modelo infla todos los intervalos.
2. **Un remuestreo que parte las componentes originales se descarta** y se sortea otro, hasta 3·B
   intentos. Si se descarta más del 5 %, toda la magnitud sale `insufficient`.
3. Remuestrear con reemplazo es multiplicar el peso de cada comparación por cuántas veces salió:
   se hace así, con `bincount`, en vez de copiar filas.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import combinations

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import csr_matrix

from aggregation import graph, support
from aggregation.estimators import bt, ordinal, simple
from aggregation.load import Row
from aggregation.params import RunParams

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

#: Los cinco niveles del tipo 3, de «gana b por mucho» (0) a «gana a por mucho» (4).
LANE_LEVELS = {"b_strong": 0, "b_slight": 1, "even": 2, "a_slight": 3, "a_strong": 4}
#: Los tres del tipo 4, en el mismo sentido: «la de abajo» (0) a «la de arriba» (2).
SYNERGY_LEVELS = {"pair_2": 0, "similar": 1, "pair_1": 2}

#: Más que esto de remuestreos descartados y la magnitud entera sale `insufficient` (§4.2).
MAX_DISCARDED = 0.05


@dataclass(frozen=True, slots=True)
class Estimate:
    """El bloque común de §4: valor, intervalo, `_n` y `_support`. Vacío no es cero (§4.5)."""

    value: float | None
    low: float | None
    high: float | None
    n: int
    support: str

    @classmethod
    def empty(cls) -> Estimate:
        return cls(None, None, None, 0, support.INSUFFICIENT)


@dataclass(slots=True)
class FitReport:
    """Lo que el Informe de Calidad de Datos de la semana 10 va a necesitar de cada ajuste."""

    name: str
    comparisons: int = 0
    components: int = 0
    attempts: int = 0
    discarded: int = 0
    failed: bool = False


@dataclass(slots=True)
class DimensionResult:
    code: str
    estimates: dict[int, Estimate]
    unknown_rate: dict[int, float | None]
    norm: dict[int, float | None]
    report: FitReport


@dataclass(frozen=True, slots=True)
class Matchup:
    a: int
    b: int
    advantage: Estimate
    observed: bool


@dataclass(slots=True)
class LaneResult:
    role: str
    estimates: dict[int, Estimate]
    matchups: list[Matchup]
    report: FitReport


#: Una dupla: dos (campeón, rol), ordenados por id de campeón.
DuoKey = tuple[tuple[int, str], tuple[int, str]]


@dataclass(frozen=True, slots=True)
class DuoEstimate:
    estimate: Estimate
    observed: bool


@dataclass(slots=True)
class DuoResult:
    context: str
    kind: str
    rows: dict[DuoKey, DuoEstimate]
    report: FitReport


@dataclass(slots=True)
class PeakResult:
    estimates: dict[int, Estimate]
    report: FitReport = field(default_factory=lambda: FitReport("peak"))


@dataclass(slots=True)
class TraitResult:
    estimates: dict[tuple[int, str], Estimate]
    report: FitReport = field(default_factory=lambda: FitReport("traits"))


# ----------------------------------------------------------------------------- piezas comunes


def _interval(samples: FloatArray) -> tuple[FloatArray, FloatArray]:
    low, high = np.percentile(samples, [2.5, 97.5], axis=0)
    return np.asarray(low, dtype=np.float64), np.asarray(high, dtype=np.float64)


def _bootstrap(
    report: FitReport,
    params: RunParams,
    rng: np.random.Generator,
    edges: IntArray,
    labels: IntArray,
    active: NDArray[np.bool_],
    refit: Callable[[FloatArray], FloatArray],
    groups: IntArray | None = None,
) -> FloatArray | None:
    """B remuestreos válidos de `refit(multiplicidades)`, o `None` si se descartaron demasiados.

    `edges[k]` son las aristas del grafo que aporta la comparación `k`, con forma `(k, e, 2)`: una
    en el 1v1 y en el tipo 1, tres en las duplas. Es lo que hace falta para decidir si el
    remuestreo conserva las componentes.

    Con `groups` —el respondedor de cada comparación— se remuestrean respondedores y no
    comparaciones: cada comparación entra tantas veces como salió su respondedor. Es la segunda
    versión del intervalo de 25 §4.7, que sólo va al informe (27 §6.2).
    """
    size = edges.shape[0]
    n_groups = 0 if groups is None else int(groups.max()) + 1
    collected: list[FloatArray] = []
    limit = 3 * params.bootstrap
    while len(collected) < params.bootstrap and report.attempts < limit:
        report.attempts += 1
        if groups is None:
            draws = np.bincount(rng.integers(0, size, size=size), minlength=size)
        else:
            draws = np.bincount(rng.integers(0, n_groups, size=n_groups), minlength=n_groups)[
                groups
            ]
        counts = draws.astype(np.float64)
        kept = edges[counts > 0].reshape(-1, 2)
        if not graph.preserved(labels, active, kept[:, 0], kept[:, 1]):
            report.discarded += 1
            continue
        collected.append(refit(counts))
    if len(collected) < params.bootstrap or report.discarded > MAX_DISCARDED * report.attempts:
        report.failed = True
        return None
    return np.vstack(collected)


def _center(values: FloatArray, labels: IntArray, anchors: NDArray[np.bool_]) -> FloatArray:
    """§4.1: cada componente se centra sobre sus campeones del pool con estimación."""
    centered = values.copy()
    for label in np.unique(labels):
        members = labels == label
        reference = members & anchors
        if not reference.any():
            reference = members
        centered[members] -= values[reference].mean()
    return centered


def _block(
    kind: str,
    params: RunParams,
    value: float,
    low: float | None,
    high: float | None,
    n: int,
    usable: bool,
) -> Estimate:
    level = support.level(params.support_thresholds, kind, n, low, high) if usable else (
        support.INSUFFICIENT
    )
    return Estimate(value, low, high, n, level)


# --------------------------------------------------------------------------- tipo 1, §5.1


def fit_dimension(
    code: str,
    rows: Sequence[Row],
    pool: Sequence[int],
    params: RunParams,
    rng: np.random.Generator,
    by_respondent: bool = False,
) -> DimensionResult:
    """§5.1. Con `by_respondent`, el intervalo sale del bootstrap por respondedor de §4.7, que
    sólo usa el Informe de Calidad de Datos (27 §6.2): los CSV nunca lo llaman así."""
    report = FitReport(f"dimension:{code}")
    decisive = [r for r in rows if r.answer.get("choice") in ("a", "b")]
    report.comparisons = len(decisive)

    # unknown_rate (§5.1): peso de los unknown sobre el peso de todas, por campeón.
    unknown: dict[int, float] = {}
    total: dict[int, float] = {}
    for r in rows:
        for champion in (r.champion_a, r.champion_b):
            if champion is None:
                continue
            total[champion] = total.get(champion, 0.0) + r.weight
            if r.answer.get("choice") == "unknown":
                unknown[champion] = unknown.get(champion, 0.0) + r.weight
    unknown_rate = {
        c: (unknown.get(c, 0.0) / total[c] if total.get(c) else None) for c in pool
    }

    nodes = sorted({c for r in decisive for c in (r.champion_a, r.champion_b) if c is not None})
    index = {c: i for i, c in enumerate(nodes)}
    n = len(nodes)
    if n == 0:
        empty = {c: Estimate.empty() for c in pool}
        return DimensionResult(code, empty, unknown_rate, dict.fromkeys(pool), report)

    first = np.array([index[r.champion_a] for r in decisive], dtype=np.int64)
    second = np.array([index[r.champion_b] for r in decisive if r.champion_b is not None])
    a_won = np.array([r.answer["choice"] == "a" for r in decisive])
    winner = np.where(a_won, first, second)
    loser = np.where(a_won, second, first)
    weights = np.array([r.weight for r in decisive])

    labels = graph.components(n, first, second)
    report.components = len(set(labels.tolist()))
    active = np.ones(n, dtype=bool)
    main = graph.largest(labels, active)
    in_pool = np.array([c in set(pool) for c in nodes])

    def solve(w: FloatArray) -> FloatArray:
        W = np.zeros((n, n))
        np.add.at(W, (winner, loser), w)
        theta = np.zeros(n)
        for label in np.unique(labels):
            members = np.flatnonzero(labels == label)
            if len(members) < 2:
                continue
            sub = W[np.ix_(members, members)]
            theta[members] = bt.mm(sub, params.bt_prior, params.max_iter, params.tol)
        return _center(theta, labels, in_pool)

    theta = solve(weights)
    edges = np.stack([first, second], axis=1)[:, None, :]
    groups: IntArray | None = None
    if by_respondent:
        people = sorted({str(r.respondent_id) for r in decisive})
        position = {p: i for i, p in enumerate(people)}
        groups = np.array([position[str(r.respondent_id)] for r in decisive], dtype=np.int64)
    samples = _bootstrap(
        report,
        params,
        rng,
        edges,
        labels,
        active,
        lambda counts: solve(weights * counts),
        groups,
    )
    low, high = _interval(samples) if samples is not None else (None, None)

    counts_n: dict[int, int] = {}
    for r in decisive:
        for champion in (r.champion_a, r.champion_b):
            if champion is not None:
                counts_n[champion] = counts_n.get(champion, 0) + 1

    estimates: dict[int, Estimate] = {}
    for c in pool:
        if c not in index:
            estimates[c] = Estimate.empty()
            continue
        i = index[c]
        usable = samples is not None and labels[i] == main
        estimates[c] = _block(
            "dimension",
            params,
            float(theta[i]),
            None if low is None else float(low[i]),
            None if high is None else float(high[i]),
            counts_n.get(c, 0),
            usable,
        )

    valued = [e.value for e in estimates.values() if e.value is not None]
    norm: dict[int, float | None] = dict.fromkeys(pool)
    if len(valued) >= 2 and max(valued) > min(valued):
        lowest, highest = min(valued), max(valued)
        for c, e in estimates.items():
            if e.value is not None:
                norm[c] = (e.value - lowest) / (highest - lowest)
    return DimensionResult(code, estimates, unknown_rate, norm, report)


def fit_dimension_by_respondent(
    code: str,
    rows: Sequence[Row],
    pool: Sequence[int],
    params: RunParams,
    rng: np.random.Generator,
) -> DimensionResult:
    """`fit_dimension` con el bootstrap por respondedor. Es una función de módulo, y no una
    `lambda`, porque el pipeline la manda a otro proceso y tiene que poder serializarse."""
    return fit_dimension(code, rows, pool, params, rng, by_respondent=True)


# ------------------------------------------------------------------ tipo 3 1v1, §5.3


def fit_lane(
    role: str,
    rows: Sequence[Row],
    pool: Sequence[int],
    roles: Mapping[int, Sequence[str]],
    params: RunParams,
    rng: np.random.Generator,
) -> LaneResult:
    report = FitReport(f"lane:{role}")
    report.comparisons = len(rows)
    nodes = sorted({c for r in rows for c in (r.champion_a, r.champion_b) if c is not None})
    index = {c: i for i, c in enumerate(nodes)}
    n = len(nodes)
    plays = {c for c in pool if role in roles.get(c, ())}
    if n == 0:
        return LaneResult(role, {c: Estimate.empty() for c in pool}, [], report)

    first = np.array([index[r.champion_a] for r in rows], dtype=np.int64)
    second = np.array([index[r.champion_b] for r in rows if r.champion_b is not None])
    levels = np.array([LANE_LEVELS[r.answer["choice"]] for r in rows], dtype=np.int64)
    weights = np.array([r.weight for r in rows])
    D = csr_matrix(
        (
            np.concatenate([np.ones(len(rows)), -np.ones(len(rows))]),
            (np.tile(np.arange(len(rows)), 2), np.concatenate([first, second])),
        ),
        shape=(len(rows), n),
    )
    labels = graph.components(n, first, second)
    report.components = len(set(labels.tolist()))
    active = np.ones(n, dtype=bool)
    main = graph.largest(labels, active)
    estimated = np.array([c in plays for c in nodes])

    # Los pares de la matriz: los dos en el pool, los dos con el rol y con fuerza estimada, y en la
    # misma componente: entre componentes no hay una escala común (ADR-008).
    pairs = [
        (index[a], index[b])
        for a, b in combinations(sorted(c for c in nodes if c in plays), 2)
        if labels[index[a]] == labels[index[b]]
    ]
    pair_first = np.array([p[0] for p in pairs], dtype=np.int64)
    pair_second = np.array([p[1] for p in pairs], dtype=np.int64)
    penalty = ordinal.epsilon_prior(params.bt_prior)

    def solve(w: FloatArray, start: FloatArray | None) -> tuple[FloatArray, FloatArray, FloatArray]:
        result = ordinal.fit(D, levels, w, 5, penalty, params.max_iter, params.tol, start)
        theta = _center(result.strengths, labels, estimated)
        delta = theta[pair_first] - theta[pair_second]
        advantage = ordinal.advantage(delta, result.thresholds) if pairs else np.zeros(0)
        raw = np.concatenate([result.strengths, result.thresholds])
        return theta, advantage, raw

    theta, advantage, start = solve(weights, None)

    def refit(counts: FloatArray) -> FloatArray:
        boot_theta, boot_advantage, _ = solve(weights * counts, start)
        return np.concatenate([boot_theta, boot_advantage])

    edges = np.stack([first, second], axis=1)[:, None, :]
    samples = _bootstrap(report, params, rng, edges, labels, active, refit)
    low, high = _interval(samples) if samples is not None else (None, None)

    counts_n: dict[int, int] = {}
    pair_n: dict[tuple[int, int], int] = {}
    for r in rows:
        assert r.champion_b is not None
        counts_n[r.champion_a] = counts_n.get(r.champion_a, 0) + 1
        counts_n[r.champion_b] = counts_n.get(r.champion_b, 0) + 1
        key = (min(r.champion_a, r.champion_b), max(r.champion_a, r.champion_b))
        pair_n[key] = pair_n.get(key, 0) + 1

    estimates: dict[int, Estimate] = {}
    for c in pool:
        if c not in index or c not in plays:
            estimates[c] = Estimate.empty()
            continue
        i = index[c]
        estimates[c] = _block(
            "lane_strength",
            params,
            float(theta[i]),
            None if low is None else float(low[i]),
            None if high is None else float(high[i]),
            counts_n.get(c, 0),
            samples is not None and labels[i] == main,
        )

    matchups: list[Matchup] = []
    for k, (i, j) in enumerate(pairs):
        a, b = nodes[i], nodes[j]
        n_pair = pair_n.get((a, b), 0)
        matchups.append(
            Matchup(
                a=a,
                b=b,
                advantage=_block(
                    "lane_strength",
                    params,
                    float(advantage[k]),
                    None if low is None else float(low[n + k]),
                    None if high is None else float(high[n + k]),
                    n_pair,
                    samples is not None and labels[i] == main,
                ),
                observed=n_pair > 0,
            )
        )
    return LaneResult(role, estimates, matchups, report)


# ------------------------------------------------------- duplas: 2v2 §5.4 y sinergia §5.5


def duo_key(first: tuple[int, str], second: tuple[int, str]) -> DuoKey:
    low, high = sorted((first, second))
    return low, high


def fit_duos(
    context: str,
    kind: str,
    context_roles: tuple[str, str],
    rows: Sequence[Row],
    pool: Sequence[int],
    roles: Mapping[int, Sequence[str]],
    params: RunParams,
    rng: np.random.Generator,
) -> DuoResult:
    """`θ_dupla = a_A + a_B + i_AB` con L2 (§5.4). `kind` es `lane` (2v2, cinco niveles) o
    `synergy` (tipo 4, tres niveles)."""
    report = FitReport(f"{kind}:{context}")
    report.comparisons = len(rows)
    if not rows:
        # Contexto sin respuestas: no se emite ninguna fila (§7).
        return DuoResult(context, kind, {}, report)

    sides: list[tuple[DuoKey, DuoKey]] = []
    for r in rows:
        assert r.champion_b is not None and r.champion_c is not None and r.champion_d is not None
        assert r.role_a and r.role_b and r.role_c and r.role_d
        top = duo_key((r.champion_a, r.role_a), (r.champion_b, r.role_b))
        bottom = duo_key((r.champion_c, r.role_c), (r.champion_d, r.role_d))
        sides.append((top, bottom))

    champions = sorted({c for pair in sides for duo in pair for c, _ in duo})
    champion_index = {c: i for i, c in enumerate(champions)}
    observed = sorted({duo for pair in sides for duo in pair})
    duo_index = {d: len(champions) + i for i, d in enumerate(observed)}
    size = len(champions) + len(observed)

    data: list[float] = []
    row_ids: list[int] = []
    col_ids: list[int] = []
    for k, (top, bottom) in enumerate(sides):
        for duo, sign in ((top, 1.0), (bottom, -1.0)):
            for champion, _ in duo:
                row_ids.append(k)
                col_ids.append(champion_index[champion])
                data.append(sign)
            row_ids.append(k)
            col_ids.append(duo_index[duo])
            data.append(sign)
    D = csr_matrix((data, (row_ids, col_ids)), shape=(len(rows), size))
    level_map = SYNERGY_LEVELS if kind == "synergy" else LANE_LEVELS
    levels = np.array([level_map[r.answer["choice"]] for r in rows], dtype=np.int64)
    n_levels = 3 if kind == "synergy" else 5
    weights = np.array([r.weight for r in rows])
    ridge = np.concatenate(
        [
            np.full(len(champions), params.lambda_champion),
            np.full(len(observed), params.lambda_interaction),
        ]
    )
    penalty = ordinal.ridge(ridge)

    # El grafo une a los cuatro campeones de cada comparación: cada dupla consigo misma y la de
    # arriba con la de abajo, tres aristas por comparación.
    edges = np.array(
        [
            [
                [champion_index[top[0][0]], champion_index[top[1][0]]],
                [champion_index[bottom[0][0]], champion_index[bottom[1][0]]],
                [champion_index[top[0][0]], champion_index[bottom[0][0]]],
            ]
            for top, bottom in sides
        ],
        dtype=np.int64,
    )
    flat = edges.reshape(-1, 2)
    labels = graph.components(len(champions), flat[:, 0], flat[:, 1])
    report.components = len(set(labels.tolist()))
    active = np.ones(len(champions), dtype=bool)
    main = graph.largest(labels, active)

    # Las filas: las duplas observadas y las combinaciones válidas del contexto con los dos
    # integrantes en el pool y con `a_·` estimada en este modelo (§5.4, nota del 29/10).
    in_pool = set(pool)
    first_role, second_role = context_roles
    candidates: set[DuoKey] = set(observed)
    estimated = [c for c in champions if c in in_pool]
    for x in estimated:
        for y in estimated:
            if x != y and first_role in roles.get(x, ()) and second_role in roles.get(y, ()):
                candidates.add(duo_key((x, first_role), (y, second_role)))
    keys = sorted(candidates)
    columns = [
        ([champion_index[c] for c, _ in key], duo_index.get(key))
        for key in keys
    ]

    def values(x: FloatArray) -> FloatArray:
        out = np.empty(len(keys))
        for k, (members, interaction) in enumerate(columns):
            out[k] = x[members].sum() + (x[interaction] if interaction is not None else 0.0)
        return out - out.mean()

    full = ordinal.fit(D, levels, weights, n_levels, penalty, params.max_iter, params.tol)
    start = np.concatenate([full.strengths, full.thresholds])
    theta = values(full.strengths)

    def refit(counts: FloatArray) -> FloatArray:
        boot = ordinal.fit(
            D, levels, weights * counts, n_levels, penalty, params.max_iter, params.tol, start
        )
        return values(boot.strengths)

    samples = _bootstrap(report, params, rng, edges, labels, active, refit)
    low, high = _interval(samples) if samples is not None else (None, None)

    duo_n: dict[DuoKey, int] = {}
    for top, bottom in sides:
        duo_n[top] = duo_n.get(top, 0) + 1
        duo_n[bottom] = duo_n.get(bottom, 0) + 1

    result: dict[DuoKey, DuoEstimate] = {}
    for k, key in enumerate(keys):
        n = duo_n.get(key, 0)
        usable = samples is not None and all(
            labels[champion_index[c]] == main for c, _ in key
        )
        result[key] = DuoEstimate(
            estimate=_block(
                "synergy",
                params,
                float(theta[k]),
                None if low is None else float(low[k]),
                None if high is None else float(high[k]),
                n,
                usable,
            ),
            observed=n > 0,
        )
    return DuoResult(context, kind, result, report)


# ----------------------------------------------------------------- tipo 2, §5.2


def fit_peaks(
    rows: Sequence[Row], pool: Sequence[int], params: RunParams, rng: np.random.Generator
) -> PeakResult:
    """Mediana ponderada por campeón e IC bootstrap sobre sus respuestas. Los campeones se
    recorren en orden de id, que es el orden en que consumen el generador."""
    by_champion: dict[int, list[tuple[float, float]]] = {}
    for r in rows:
        by_champion.setdefault(r.champion_a, []).append((float(r.answer["minute"]), r.weight))
    report = FitReport("peak", comparisons=len(rows))
    estimates: dict[int, Estimate] = {}
    for c in sorted(pool):
        answers = by_champion.get(c)
        if not answers:
            estimates[c] = Estimate.empty()
            continue
        minutes = np.array([m for m, _ in answers])
        weights = np.array([w for _, w in answers])
        peak = simple.round_half_up(simple.weighted_median(minutes, weights))
        medians = np.empty(params.bootstrap)
        for b in range(params.bootstrap):
            idx = rng.integers(0, len(answers), size=len(answers))
            medians[b] = simple.weighted_median(minutes[idx], weights[idx])
        low, high = np.percentile(medians, [2.5, 97.5])
        ci_low, ci_high = simple.round_half_up(float(low)), simple.round_half_up(float(high))
        estimates[c] = Estimate(
            float(peak),
            float(ci_low),
            float(ci_high),
            len(answers),
            support.level(params.support_thresholds, "peak_minute", len(answers), ci_low, ci_high),
        )
    return PeakResult(estimates, report)


# ----------------------------------------------------------------- tipo 5, §5.6


def fit_traits(
    rows: Sequence[Row], pool: Sequence[int], traits: Sequence[str], params: RunParams
) -> TraitResult:
    by_champion: dict[int, list[tuple[set[str], float]]] = {}
    for r in rows:
        by_champion.setdefault(r.champion_a, []).append((set(r.answer["traits"]), r.weight))
    estimates: dict[tuple[int, str], Estimate] = {}
    for c in pool:
        answers = by_champion.get(c, [])
        for trait in traits:
            if not answers:
                estimates[(c, trait)] = Estimate.empty()
                continue
            weights = [w for _, w in answers]
            marked = sum(w for chosen, w in answers if trait in chosen)
            p = marked / sum(weights)
            low, high = simple.wilson(p, simple.kish(weights))
            estimates[(c, trait)] = Estimate(
                p,
                low,
                high,
                len(answers),
                support.level(params.support_thresholds, "trait", len(answers), low, high),
            )
    return TraitResult(estimates, FitReport("traits", comparisons=len(rows)))
