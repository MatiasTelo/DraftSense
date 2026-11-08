"""Acuerdo inter-anotador de cada magnitud (`docs/27-validacion-confiabilidad.md` §2.3).

Sobre las filas de la corrida, sin ponderar. **La orientación es lo que más fácil se rompe**: si el
par se presentó con el campeón (o la dupla) de mayor id primero, el nivel se espeja. Sin eso, dos
personas que opinan lo mismo sobre preguntas armadas al revés contarían como desacuerdo, y el alfa
saldría más bajo sin que nada falle.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass

from aggregation.fits import LANE_LEVELS, SYNERGY_LEVELS, DuoKey, duo_key
from aggregation.load import Dataset, Row
from aggregation.quality.krippendorff import Alpha, Scale, alpha
from aggregation.writers import LANE_ROLES
from app.models import QuestionType

#: Los umbrales de Krippendorff que el informe reporta, sin tocar los CSV (27 §2.4).
RELIABLE = 0.800
TENTATIVE = 0.667

#: Los tres contextos de dupla, en el orden de `pipeline.DUO_CONTEXTS`.
DUO_CONTEXTS = ("bot", "top_jungle", "mid_jungle")


@dataclass(frozen=True, slots=True)
class Agreement:
    magnitude: str
    scale: Scale
    result: Alpha

    @property
    def reading(self) -> str:
        value = self.result.value
        if value is None:
            return "no calculable"
        if value >= RELIABLE:
            return "confiable"
        if value >= TENTATIVE:
            return "tentativo"
        return "no confiable"


def _units(pairs: Iterable[tuple[Hashable, Hashable]]) -> list[list[Hashable]]:
    grouped: dict[Hashable, list[Hashable]] = defaultdict(list)
    for unit, value in pairs:
        grouped[unit].append(value)
    # El orden de las unidades no cambia el resultado, pero sí el de la suma en coma flotante.
    return [grouped[unit] for unit in sorted(grouped, key=repr)]


def _duos(r: Row) -> tuple[DuoKey, DuoKey]:
    assert r.champion_b is not None and r.champion_c is not None and r.champion_d is not None
    assert r.role_a and r.role_b and r.role_c and r.role_d
    top = duo_key((r.champion_a, r.role_a), (r.champion_b, r.role_b))
    bottom = duo_key((r.champion_c, r.role_c), (r.champion_d, r.role_d))
    return top, bottom


def _pairwise(rows: Sequence[Row]) -> list[list[Hashable]]:
    def side(r: Row) -> tuple[Hashable, Hashable]:
        assert r.champion_b is not None
        low, high = sorted((r.champion_a, r.champion_b))
        chosen = r.champion_a if r.answer["choice"] == "a" else r.champion_b
        return (low, high), "low" if chosen == low else "high"

    return _units(side(r) for r in rows if r.answer.get("choice") in ("a", "b"))


def _lane(rows: Sequence[Row]) -> list[list[Hashable]]:
    def level(r: Row) -> tuple[Hashable, Hashable]:
        assert r.champion_b is not None
        value = LANE_LEVELS[r.answer["choice"]]
        if r.champion_a > r.champion_b:
            return (r.champion_b, r.champion_a), 4 - value
        return (r.champion_a, r.champion_b), value

    return _units(level(r) for r in rows)


def _duo(rows: Sequence[Row], levels: dict[str, int]) -> list[list[Hashable]]:
    top_level = max(levels.values())

    def level(r: Row) -> tuple[Hashable, Hashable]:
        top, bottom = _duos(r)
        value = levels[r.answer["choice"]]
        if top > bottom:
            return (bottom, top), top_level - value
        return (top, bottom), value

    return _units(level(r) for r in rows)


def compute(data: Dataset) -> list[Agreement]:
    """Una alfa por magnitud, en el orden de los CSV: dimensiones, pico, roles del 1v1, 2v2,
    sinergia por contexto y atributos."""
    by_type: dict[QuestionType, list[Row]] = defaultdict(list)
    for r in data.rows:
        by_type[r.type].append(r)
    result: list[Agreement] = []

    for dimension_id, code in data.dimensions:
        rows = [
            r for r in by_type[QuestionType.PAIRWISE_DIMENSION] if r.dimension_id == dimension_id
        ]
        result.append(Agreement(f"score · {code}", "nominal", alpha(_pairwise(rows), "nominal")))

    peaks = _units(
        (r.champion_a, int(r.answer["minute"])) for r in by_type[QuestionType.PEAK_TIMING]
    )
    result.append(Agreement("peak_minute", "interval", alpha(peaks, "interval")))

    lanes = by_type[QuestionType.LANE_MATCHUP]
    ordinal = list(range(5))
    for role in LANE_ROLES:
        rows = [r for r in lanes if r.champion_c is None and r.role == role]
        result.append(
            Agreement(f"lane_strength · {role}", "ordinal", alpha(_lane(rows), "ordinal", ordinal))
        )
    bot = [r for r in lanes if r.champion_c is not None]
    result.append(
        Agreement(
            "duo lane_strength · bot", "ordinal", alpha(_duo(bot, LANE_LEVELS), "ordinal", ordinal)
        )
    )

    for context in DUO_CONTEXTS:
        rows = [r for r in by_type[QuestionType.DUO_SYNERGY] if r.duo_ctx == context]
        result.append(
            Agreement(
                f"synergy · {context}",
                "nominal",
                alpha(_duo(rows, SYNERGY_LEVELS), "nominal", [0, 1, 2]),
            )
        )

    traits = by_type[QuestionType.TRAIT_MULTISELECT]
    for trait in data.traits:
        units = _units((r.champion_a, trait in r.answer["traits"]) for r in traits)
        result.append(
            Agreement(f"proportion · {trait}", "nominal", alpha(units, "nominal", [False, True]))
        )
    return result
