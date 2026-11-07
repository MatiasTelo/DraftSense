"""Las métricas del informe que no son el alfa ni los segmentos (`docs/27-...` §3 a §8).

Cada función recibe datos ya cargados y devuelve filas listas para el informe. Ninguna toca la
base ni el generador: por eso el informe es tan reproducible como los CSV (CA-415).
"""

from __future__ import annotations

import math
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.stats import spearmanr

from aggregation.fits import (
    DimensionResult,
    DuoKey,
    DuoResult,
    Estimate,
    FitReport,
    LaneResult,
    PeakResult,
    TraitResult,
    duo_key,
)
from aggregation.load import ChampionInfo, Dataset, Row
from aggregation.quality.agreement import DUO_CONTEXTS
from aggregation.quality.data import Extra, Person
from aggregation.quality.segments import RANK_SEGMENTS, UNDECLARED, segment_of
from aggregation.writers import LANE_ROLES
from app.models import QuestionType
from app.models.collection import VALID_HOURS_BUCKETS, VALID_RANKS

#: Los roles de cada contexto de dupla (ADR-026), como en `pipeline.DUO_CONTEXTS`.
DUO_ROLES: dict[str, tuple[str, str]] = {
    "bot": ("adc", "support"),
    "top_jungle": ("top", "jungle"),
    "mid_jungle": ("mid", "jungle"),
}
#: El orden del enum `lane_role` del esquema.
ROLE_VALUES = ("top", "jungle", "mid", "adc", "support")
#: El criterio de 25 §4.7.
CONCENTRATION_LIMIT = 0.40

RETEST_KINDS = (
    ("pairwise_dimension", "Tipo 1 — ranking"),
    ("peak_timing", "Tipo 2 — pico"),
    ("lane_1v1", "Tipo 3 — 1v1"),
    ("lane_2v2", "Tipo 3 — 2v2"),
    ("duo_synergy", "Tipo 4 — sinergia"),
    ("trait_multiselect", "Tipo 5 — atributos"),
)


@dataclass(frozen=True, slots=True)
class Results:
    """Los ajustes de la corrida, como los recibe `writers`."""

    dimensions: Sequence[DimensionResult]
    lanes: Mapping[str, LaneResult]
    bot_lane: DuoResult
    synergy: Sequence[DuoResult]
    peak: PeakResult
    traits: TraitResult

    def reports(self) -> list[FitReport]:
        return [
            *(d.report for d in self.dimensions),
            *(self.lanes[role].report for role in LANE_ROLES),
            self.bot_lane.report,
            *(s.report for s in self.synergy),
            self.peak.report,
            self.traits.report,
        ]


def rate(part: int, whole: int) -> float | None:
    return None if whole == 0 else part / whole


# --------------------------------------------------------------------------- test-retest, §3


@dataclass(frozen=True, slots=True)
class Retest:
    label: str
    pairs: int
    consistent: int


def retest(extra: Extra) -> list[Retest]:
    counted = [p for p in extra.retests if p.consistent is not None]
    out = []
    for kind, label in RETEST_KINDS:
        mine = [p for p in counted if p.kind == kind]
        out.append(Retest(label, len(mine), sum(1 for p in mine if p.consistent)))
    return out


def consistency_by_respondent(extra: Extra) -> dict[uuid.UUID, tuple[int, int]]:
    """`(consistentes, pares)` de cada respondedor en la ventana."""
    totals: dict[uuid.UUID, list[int]] = defaultdict(lambda: [0, 0])
    for p in extra.retests:
        if p.consistent is None:
            continue
        totals[p.respondent_id][1] += 1
        if p.consistent:
            totals[p.respondent_id][0] += 1
    return {k: (v[0], v[1]) for k, v in totals.items()}


# ----------------------------------------------------------------------------- honeypots, §4


@dataclass(frozen=True, slots=True)
class HoneypotRow:
    question_id: int
    label: str
    patch: str
    attempts: int
    passed: int
    #: `(intentos, aprobadas)` por segmento de rango, en el orden de 25 §3.5.
    by_segment: list[tuple[str, int, int]]
    #: El cruce de 27 §4.3, sólo con el piso de intentos: `(consistentes, pares)` de cada grupo.
    failers: tuple[int, int] | None
    passers: tuple[int, int] | None

    @property
    def suspicious(self) -> bool:
        if self.failers is None or self.passers is None:
            return False
        if self.failers[1] == 0 or self.passers[1] == 0:
            return False
        return self.failers[0] / self.failers[1] >= self.passers[0] / self.passers[1]


def honeypots(extra: Extra, champions: Mapping[int, ChampionInfo]) -> list[HoneypotRow]:
    consistency = consistency_by_respondent(extra)
    segments = [*RANK_SEGMENTS, UNDECLARED]
    by_question: dict[int, list[tuple[uuid.UUID, bool]]] = defaultdict(list)
    for answer in extra.honeypot_answers:
        if answer.passed is not None:
            by_question[answer.question_id].append((answer.respondent_id, answer.passed))

    out = []
    for question_id, honeypot in sorted(extra.honeypots.items()):
        answers = by_question.get(question_id, [])
        if not answers:
            continue
        seg_counts = []
        for segment in segments:
            mine = [
                ok for who, ok in answers if segment_of("rank", extra.people.get(who)) == segment
            ]
            seg_counts.append((segment, len(mine), sum(mine)))

        failers = passers = None
        if len(answers) >= extra.settings.honeypot_min_attempts:
            failers = _pooled(consistency, (who for who, ok in answers if not ok))
            passers = _pooled(consistency, (who for who, ok in answers if ok))
        a = champions[honeypot.champion_a].display_name
        b = champions[honeypot.champion_b].display_name
        out.append(
            HoneypotRow(
                question_id=question_id,
                label=f"{honeypot.dimension}: {a} vs {b}",
                patch=honeypot.patch,
                attempts=len(answers),
                passed=sum(ok for _, ok in answers),
                by_segment=seg_counts,
                failers=failers,
                passers=passers,
            )
        )
    return out


def _pooled(
    consistency: Mapping[uuid.UUID, tuple[int, int]], people: Iterable[uuid.UUID]
) -> tuple[int, int]:
    consistent = pairs = 0
    for who in people:
        c, p = consistency.get(who, (0, 0))
        consistent += c
        pairs += p
    return consistent, pairs


# ----------------------------------------------------------------------------- cobertura, §5


@dataclass(frozen=True, slots=True)
class PairCoverage:
    magnitude: str
    possible: int
    observed: int
    #: Mínimo, mediana y máximo de comparaciones por par observado.
    spread: tuple[int, float, int] | None


def _spread(counts: Sequence[int]) -> tuple[int, float, int] | None:
    if not counts:
        return None
    return min(counts), float(np.median(counts)), max(counts)


def _duo_sides(r: Row) -> tuple[DuoKey, DuoKey]:
    assert r.champion_b is not None and r.champion_c is not None and r.champion_d is not None
    assert r.role_a and r.role_b and r.role_c and r.role_d
    return (
        duo_key((r.champion_a, r.role_a), (r.champion_b, r.role_b)),
        duo_key((r.champion_c, r.role_c), (r.champion_d, r.role_d)),
    )


def coverage(data: Dataset) -> list[PairCoverage]:
    pool = set(data.pool)
    roles = {c: data.champions[c].roles for c in data.pool}
    out = []

    def pairs(rows: Iterable[Row], members: set[int]) -> Counter[tuple[int, int]]:
        counter: Counter[tuple[int, int]] = Counter()
        for r in rows:
            assert r.champion_b is not None
            low, high = sorted((r.champion_a, r.champion_b))
            if low in members and high in members:
                counter[(low, high)] += 1
        return counter

    for dimension_id, code in data.dimensions:
        rows = [
            r
            for r in data.rows
            if r.type is QuestionType.PAIRWISE_DIMENSION
            and r.dimension_id == dimension_id
            and r.answer.get("choice") in ("a", "b")
        ]
        seen = pairs(rows, pool)
        out.append(
            PairCoverage(
                f"score · {code}", math.comb(len(pool), 2), len(seen), _spread(list(seen.values()))
            )
        )

    lanes = [r for r in data.rows if r.type is QuestionType.LANE_MATCHUP]
    for role in LANE_ROLES:
        members = {c for c in pool if role in roles[c]}
        seen = pairs((r for r in lanes if r.champion_c is None and r.role == role), members)
        out.append(
            PairCoverage(
                f"lane_strength · {role}",
                math.comb(len(members), 2),
                len(seen),
                _spread(list(seen.values())),
            )
        )

    def duos(label: str, rows: Iterable[Row], context: str) -> PairCoverage:
        first, second = DUO_ROLES[context]
        possible = {
            duo_key((x, first), (y, second))
            for x in pool
            for y in pool
            if x != y and first in roles[x] and second in roles[y]
        }
        counter: Counter[DuoKey] = Counter()
        for r in rows:
            for side in _duo_sides(r):
                if side in possible:
                    counter[side] += 1
        return PairCoverage(label, len(possible), len(counter), _spread(list(counter.values())))

    bot = [r for r in lanes if r.champion_c is not None]
    out.append(duos("duo lane_strength · bot", bot, "bot"))
    for context in DUO_CONTEXTS:
        rows = [r for r in data.rows if r.type is QuestionType.DUO_SYNERGY and r.duo_ctx == context]
        out.append(duos(f"synergy · {context}", rows, context))
    return out


@dataclass(frozen=True, slots=True)
class Magnitude:
    """Las filas de una magnitud de los CSV: lo que necesitan el soporte y el ancho medio."""

    name: str
    unit: str
    estimates: list[Estimate]

    def support(self) -> tuple[int, int, int]:
        levels = Counter(e.support for e in self.estimates)
        return levels["solid"], levels["limited"], levels["insufficient"]

    def mean_width(self) -> float | None:
        widths = [
            e.high - e.low for e in self.estimates if e.low is not None and e.high is not None
        ]
        return None if not widths else float(np.mean(widths))


def magnitudes(data: Dataset, results: Results) -> list[Magnitude]:
    """Las magnitudes de los seis CSV, en su orden (25 §4.6)."""
    pool = data.pool
    out = [
        Magnitude(f"score · {d.code}", "log-odds", [d.estimates[c] for c in pool])
        for d in results.dimensions
    ]
    out.append(Magnitude("peak_minute", "minutos", [results.peak.estimates[c] for c in pool]))
    for role in LANE_ROLES:
        lane = results.lanes[role]
        out.append(
            Magnitude(
                f"lane_strength · {role}",
                "log-odds",
                [lane.estimates.get(c, Estimate.empty()) for c in pool],
            )
        )
    for trait in data.traits:
        out.append(
            Magnitude(
                f"proportion · {trait}",
                "proporción",
                [results.traits.estimates[(c, trait)] for c in pool],
            )
        )
    for role in LANE_ROLES:
        lane = results.lanes[role]
        out.append(
            Magnitude(
                f"advantage · {role}",
                "−1…+1",
                [m.advantage for m in sorted(lane.matchups, key=lambda m: (m.a, m.b))],
            )
        )
    for synergy in results.synergy:
        out.append(
            Magnitude(
                f"synergy · {synergy.context}",
                "log-odds",
                [v.estimate for _, v in sorted(synergy.rows.items())],
            )
        )
    out.append(
        Magnitude(
            "duo lane_strength · bot",
            "log-odds",
            [v.estimate for _, v in sorted(results.bot_lane.rows.items())],
        )
    )
    return out


def wide_peaks(
    data: Dataset, results: Results, thresholds: Mapping[str, Mapping[str, Mapping[str, float]]]
) -> list[str]:
    """Picos con la `n` de `solid` y un intervalo más ancho: la firma de una bimodal (27 §5.4)."""
    rule = thresholds["peak_minute"]["solid"]
    out = []
    for c in data.pool:
        e = results.peak.estimates[c]
        if e.low is None or e.high is None:
            continue
        if e.n >= rule["n"] and e.high - e.low > rule["width"]:
            out.append(data.champions[c].display_name)
    return out


def uneven_traits(data: Dataset, results: Results) -> list[str]:
    """Campeones cuyos `proportion_n` difieren entre atributos (25 §5.6)."""
    out = []
    for c in data.pool:
        counts = {results.traits.estimates[(c, t)].n for t in data.traits}
        if len(counts) > 1:
            out.append(data.champions[c].display_name)
    return out


# ------------------------------------------------------------------------- incertidumbre, §6


@dataclass(frozen=True, slots=True)
class Concentration:
    respondents: int
    top: int
    rows: int
    top_rows: int

    @property
    def index(self) -> float | None:
        return rate(self.top_rows, self.rows)


def concentration(rows: Sequence[Row]) -> Concentration:
    """Qué fracción aporta el decil más activo: los `⌈N/10⌉` con más filas (27 §6.3)."""
    counts = sorted(Counter(r.respondent_id for r in rows).values(), reverse=True)
    top = math.ceil(len(counts) / 10)
    return Concentration(len(counts), top, len(rows), sum(counts[:top]))


def decisive(rows: Sequence[Row]) -> list[Row]:
    return [
        r
        for r in rows
        if r.type is QuestionType.PAIRWISE_DIMENSION and r.answer.get("choice") in ("a", "b")
    ]


# ------------------------------------------------------------------- datos declarados, §7


@dataclass(frozen=True, slots=True)
class SampleRow:
    value: str
    respondents: int
    responses: int


def sample(data: Dataset, people: Mapping[uuid.UUID, Person]) -> dict[str, list[SampleRow]]:
    """Las tres tablas de 25 §3.4, sobre la gente y las filas de la corrida."""
    per_person = Counter(r.respondent_id for r in data.rows)
    variables: dict[str, tuple[Sequence[str], str]] = {
        "Rango": (VALID_RANKS, "rank"),
        "Rol principal": (ROLE_VALUES, "main_role"),
        "Horas por semana": (VALID_HOURS_BUCKETS, "hours"),
    }
    out = {}
    for title, (values, attribute) in variables.items():
        respondents: Counter[str | None] = Counter()
        responses: Counter[str | None] = Counter()
        for who, n in per_person.items():
            person = people.get(who)
            value = None if person is None else getattr(person, attribute)
            respondents[value] += 1
            responses[value] += n
        out[title] = [SampleRow(v, respondents[v], responses[v]) for v in values] + [
            SampleRow("(no dijo)", respondents[None], responses[None])
        ]
    return out


def omitted_onboarding(data: Dataset, people: Mapping[uuid.UUID, Person]) -> tuple[int, int]:
    """`(sin ninguno de los tres datos, respondedores)`: el tamaño de `undeclared` (25 §3.9)."""
    who = {r.respondent_id for r in data.rows}
    none = sum(
        1
        for w in who
        if (p := people.get(w)) is None
        or (p.rank is None and p.main_role is None and p.hours is None)
    )
    return none, len(who)


@dataclass(frozen=True, slots=True)
class RoleCoverage:
    magnitude: str
    responses: int
    mains: int
    undeclared: int


def role_coverage(data: Dataset, people: Mapping[uuid.UUID, Person]) -> list[RoleCoverage]:
    """25 §3.6: qué parte de las opiniones sobre un carril vino de quien lo juega."""

    def role(r: Row) -> str | None:
        p = people.get(r.respondent_id)
        return None if p is None else p.main_role

    lanes = [r for r in data.rows if r.type is QuestionType.LANE_MATCHUP]
    out = []
    for lane in LANE_ROLES:
        rows = [r for r in lanes if r.champion_c is None and r.role == lane]
        out.append(
            RoleCoverage(
                f"lane_strength · {lane}",
                len(rows),
                sum(1 for r in rows if role(r) == lane),
                sum(1 for r in rows if role(r) is None),
            )
        )
    bot = [r for r in lanes if r.champion_c is not None]
    out.append(
        RoleCoverage(
            "duo lane_strength · bot (adc o support)",
            len(bot),
            sum(1 for r in bot if role(r) in ("adc", "support")),
            sum(1 for r in bot if role(r) is None),
        )
    )
    return out


@dataclass(frozen=True, slots=True)
class TrustBucket:
    bucket: str
    n: int
    quantiles: tuple[float, float, float, float, float] | None


def trust_by_hours(extra: Extra) -> tuple[list[TrustBucket], float | None, int]:
    """25 §3.7 sobre los no marcados de la ventana, sin filtro de trust (27 §7.4)."""
    people = [p for p in extra.people.values() if not p.flagged]
    out = []
    for bucket in [*VALID_HOURS_BUCKETS, None]:
        values = sorted(p.trust for p in people if p.hours == bucket)
        quantiles = None
        if values:
            q = np.percentile(values, [0, 25, 50, 75, 100])
            quantiles = (float(q[0]), float(q[1]), float(q[2]), float(q[3]), float(q[4]))
        out.append(TrustBucket("(no dijo)" if bucket is None else bucket, len(values), quantiles))

    order = {bucket: i for i, bucket in enumerate(VALID_HOURS_BUCKETS)}
    declared = [(order[p.hours], p.trust) for p in people if p.hours is not None]
    rho = None
    if len(declared) >= 3:
        x = np.array([d[0] for d in declared], dtype=np.float64)
        y = np.array([d[1] for d in declared], dtype=np.float64)
        if np.ptp(x) > 0 and np.ptp(y) > 0:
            value = float(spearmanr(x, y).statistic)
            rho = None if math.isnan(value) else value
    return out, rho, len(declared)
