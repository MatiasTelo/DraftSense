"""`python -m aggregation.compare_truth` — ¿el pipeline recupera la verdad de la seed sintética?

Lee el JSON que escribe `draftsense seed-synthetic-responses` y los seis CSV de una corrida, y
compara magnitud por magnitud. **No es parte del contrato de salida**: es la herramienta para
probar el pipeline sin piloto (decisión del alumno del 29/10/2026).

Se informa sobre todo el **orden** (ρ de Spearman), porque la escala no tiene por qué coincidir:
los respondedores ruidosos y los al azar contestan con menos señal que la verdad, y eso encoge los
scores estimados hacia 0 sin cambiar el orden. Para el pico y los atributos, que tienen escala
propia, se informa además el error absoluto medio y cuántas veces el intervalo contiene la verdad.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from scipy.stats import spearmanr

LANE_VALUES = (-1.0, -0.5, 0.0, 0.5, 1.0)


def _read(folder: Path, kind: str) -> list[dict[str, str]]:
    [path] = sorted(folder.glob(f"{kind}_v*.csv"))
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _rho(estimated: Sequence[float], truth: Sequence[float]) -> float:
    if len(estimated) < 3:
        return math.nan
    return float(spearmanr(estimated, truth).statistic)


def _duo_truth(model: dict[str, dict[str, float]], label: str) -> float:
    members = [part.split(":")[0] for part in label.split("|")]
    return sum(model["a"].get(c, 0.0) for c in members) + model["i"].get(label, 0.0)


def _expected_margin(delta: float, tau1: float, tau2: float) -> float:
    def sig(x: float) -> float:
        return 1 / (1 + math.exp(-x))

    exceed = [sig(delta - t) for t in (-tau2, -tau1, tau1, tau2)]
    cumulative = [1.0, *exceed, 0.0]
    probs = [cumulative[k] - cumulative[k + 1] for k in range(5)]
    return sum(v * p for v, p in zip(LANE_VALUES, probs, strict=True))


def compare(truth: dict[str, Any], folder: Path) -> list[str]:
    lines: list[str] = []

    rows = _read(folder, "champion_dimensions")
    for code, values in truth["dimensions"].items():
        pairs = [
            (float(r["score"]), values[r["champion_id"]])
            for r in rows
            if r["dimension"] == code and r["score"]
        ]
        solid = sum(1 for r in rows if r["dimension"] == code and r["score_support"] == "solid")
        estimated, real = zip(*pairs, strict=True) if pairs else ((), ())
        lines.append(
            f"dimensión {code:<10} ρ = {_rho(estimated, real):.3f}  "
            f"({len(pairs)} campeones, {solid} solid)"
        )

    rows = _read(folder, "peak_timing")
    errors, covered, total = [], 0, 0
    for r in rows:
        if not r["peak_minute"]:
            continue
        real = truth["peak"][r["champion_id"]]
        errors.append(abs(int(r["peak_minute"]) - real))
        covered += int(int(r["peak_minute_ci_low"]) <= real <= int(r["peak_minute_ci_high"]))
        total += 1
    if total:
        lines.append(
            f"pico          error medio {statistics.mean(errors):.2f} min, "
            f"IC contiene la verdad en {covered}/{total}"
        )

    rows = _read(folder, "champion_lane_strength")
    for role, values in truth["lane"].items():
        pairs = [
            (float(r["lane_strength"]), values[r["champion_id"]])
            for r in rows
            if r["role"] == role and r["lane_strength"] and r["champion_id"] in values
        ]
        estimated, real = zip(*pairs, strict=True) if pairs else ((), ())
        lines.append(f"línea {role:<8} ρ = {_rho(estimated, real):.3f}  ({len(pairs)} campeones)")

    rows = _read(folder, "matchup_matrix")
    tau1, tau2 = truth["lane_thresholds"]
    pairs = []
    for r in rows:
        values = truth["lane"].get(r["role"], {})
        if r["champion_a_id"] in values and r["champion_b_id"] in values:
            delta = values[r["champion_a_id"]] - values[r["champion_b_id"]]
            pairs.append((float(r["advantage"]), _expected_margin(delta, tau1, tau2)))
    if pairs:
        estimated, real = zip(*pairs, strict=True)
        lines.append(f"matchups      ρ = {_rho(estimated, real):.3f}  ({len(pairs)} pares)")

    rows = _read(folder, "duo_features")
    contexts = {("adc", "support"): "bot", ("top", "jungle"): "top_jungle",
                ("mid", "jungle"): "mid_jungle"}
    for (first, second), context in contexts.items():
        model = truth["synergy"].get(context)
        if model is None:
            continue
        pairs = []
        lane_pairs = []
        for r in rows:
            if {r["role_a"], r["role_b"]} != {first, second}:
                continue
            label = "|".join(
                sorted(
                    (f"{r['champion_a_id']}:{r['role_a']}", f"{r['champion_b_id']}:{r['role_b']}"),
                    key=lambda part: int(part.split(":")[0]),
                )
            )
            if r["synergy"] and r["synergy_is_observed"] == "true":
                pairs.append((float(r["synergy"]), _duo_truth(model, label)))
            if context == "bot" and r["lane_strength"] and r["lane_strength_is_observed"] == "true":
                lane_pairs.append((float(r["lane_strength"]), _duo_truth(truth["bot_lane"], label)))
        if pairs:
            estimated, real = zip(*pairs, strict=True)
            lines.append(
                f"sinergia {context:<10} ρ = {_rho(estimated, real):.3f}  "
                f"({len(pairs)} duplas observadas)"
            )
        if lane_pairs:
            estimated, real = zip(*lane_pairs, strict=True)
            lines.append(
                f"línea 2v2 bot       ρ = {_rho(estimated, real):.3f}  "
                f"({len(lane_pairs)} duplas observadas)"
            )

    rows = _read(folder, "champion_traits")
    errors, covered, total = [], 0, 0
    estimated_values, real_values = [], []
    for r in rows:
        if not r["proportion"]:
            continue
        real = truth["traits"][r["champion_id"]][r["trait"]]
        value = float(r["proportion"])
        errors.append(abs(value - real))
        estimated_values.append(value)
        real_values.append(real)
        covered += int(float(r["proportion_ci_low"]) <= real <= float(r["proportion_ci_high"]))
        total += 1
    if total:
        lines.append(
            f"atributos     ρ = {_rho(estimated_values, real_values):.3f}, error medio "
            f"{statistics.mean(errors):.3f}, IC contiene la verdad en {covered}/{total}"
        )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m aggregation.compare_truth")
    parser.add_argument("--truth", type=Path, required=True, help="JSON de la seed sintética")
    parser.add_argument("--exports", type=Path, required=True, help="carpeta con los seis CSV")
    args = parser.parse_args()
    truth = json.loads(args.truth.read_text(encoding="utf-8"))
    for line in compare(truth, args.exports):
        print(line)
    sys.exit(0)


if __name__ == "__main__":
    main()
