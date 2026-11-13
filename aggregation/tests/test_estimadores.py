"""Los estimadores sin base: `docs/25-agregacion.md` §11 y CA-401 a CA-406 de
`docs/03-criterios-aceptacion.md` §5."""

from __future__ import annotations

import csv
import itertools
import math
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import choix
import numpy as np
import pytest

from aggregation import fits, graph, support, writers
from aggregation.estimators import bt, ordinal, simple
from aggregation.load import Row
from aggregation.params import DEFAULT_SUPPORT_THRESHOLDS, RunParams, parse_window
from app.models import QuestionType

EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples"


def params(bootstrap: int = 60, **changes: Any) -> RunParams:
    values: dict[str, Any] = {
        "patch_from": "16.18",
        "patch_to": "16.20",
        "min_trust": Decimal("0.300"),
        "halflife": 21.0,
        "sigma": 7.5,
        "bootstrap": bootstrap,
        "exported_at": __import__("datetime").date(2026, 11, 10),
        "bt_prior": 0.5,
        "lambda_champion": 0.10,
        "lambda_interaction": 1.00,
        "max_iter": 500,
        "tol": 1e-9,
        "support_thresholds": DEFAULT_SUPPORT_THRESHOLDS,
    }
    values.update(changes)
    return RunParams(**values)


_ids = itertools.count(1)


def row(
    question_type: QuestionType, answer: dict[str, Any], weight: float = 1.0, **cols: Any
) -> Row:
    defaults: dict[str, Any] = {
        "champion_b": None,
        "champion_c": None,
        "champion_d": None,
        "dimension_id": None,
        "role": None,
        "duo_ctx": None,
        "role_a": None,
        "role_b": None,
        "role_c": None,
        "role_d": None,
    }
    defaults.update(cols)
    return Row(
        response_id=next(_ids),
        respondent_id=uuid.uuid4(),
        patch_id=1,
        type=question_type,
        answer=answer,
        weight=weight,
        **defaults,
    )


def duel(winner: int, loser: int, weight: float = 1.0) -> Row:
    low, high = sorted((winner, loser))
    return row(
        QuestionType.PAIRWISE_DIMENSION,
        {"choice": "a" if winner == low else "b"},
        weight,
        champion_a=low,
        champion_b=high,
        dimension_id=1,
    )


def rng() -> np.random.Generator:
    return np.random.default_rng(7)


# ------------------------------------------------------------------------------- Bradley-Terry


def test_ca401_el_orden_es_coherente() -> None:
    """A le gana a B y B a C ⇒ θ_A > θ_B > θ_C."""
    rows = [duel(1, 2)] * 8 + [duel(2, 1)] * 2 + [duel(2, 3)] * 8 + [duel(3, 2)] * 2
    rows += [duel(1, 3)] * 9 + [duel(3, 1)]
    result = fits.fit_dimension("x", rows, [1, 2, 3], params(), rng())
    scores = {c: e.value for c, e in result.estimates.items()}
    assert scores[1] is not None and scores[2] is not None and scores[3] is not None
    assert scores[1] > scores[2] > scores[3]
    assert abs(sum(v for v in scores.values() if v is not None)) < 1e-9


def test_el_mm_coincide_con_choix_sin_epsilon() -> None:
    """§5.1: el pseudocódigo es la definición y choix la verificación (§8.2, nota del 29/10)."""
    generator = np.random.default_rng(3)
    W = generator.integers(1, 9, size=(5, 5)).astype(float)
    np.fill_diagonal(W, 0)
    ours = bt.mm(W, eps=0.0, max_iter=10_000, tol=1e-12)
    theirs = choix.ilsr_pairwise_dense(W, alpha=0.0)
    assert np.allclose(ours - ours.mean(), theirs - theirs.mean(), atol=1e-5)


def test_el_epsilon_mantiene_finito_a_un_invicto() -> None:
    W = np.array([[0.0, 5.0], [0.0, 0.0]])
    theta = bt.mm(W, eps=0.5, max_iter=500, tol=1e-9)
    assert np.all(np.isfinite(theta))
    assert theta[0] > theta[1]


def test_ca402_el_trust_pondera() -> None:
    """Las mismas comparaciones con más peso del lado de B mueven el score hacia B."""
    base = [duel(1, 2, 1.0)] * 5 + [duel(2, 1, 1.0)] * 5 + [duel(1, 3)] * 5 + [duel(3, 2)] * 5
    heavier = [duel(1, 2, 1.0)] * 5 + [duel(2, 1, 3.0)] * 5 + [duel(1, 3)] * 5 + [duel(3, 2)] * 5
    even = fits.fit_dimension("x", base, [1, 2, 3], params(), rng()).estimates
    tilted = fits.fit_dimension("x", heavier, [1, 2, 3], params(), rng()).estimates
    assert (tilted[2].value or 0) - (tilted[1].value or 0) > (even[2].value or 0) - (
        even[1].value or 0
    )


def test_ca403_dos_componentes_se_reportan_sin_orden_global() -> None:
    """ADR-008: cada componente se centra sola; lo que queda fuera de la mayor es insufficient."""
    rows = [duel(1, 2)] * 20 + [duel(2, 3)] * 20 + [duel(3, 1)] * 20
    rows += [duel(4, 5)] * 15 + [duel(5, 4)] * 5
    result = fits.fit_dimension("x", rows, [1, 2, 3, 4, 5], params(), rng())
    assert result.report.components == 2
    small = [result.estimates[4], result.estimates[5]]
    assert all(e.support == support.INSUFFICIENT for e in small)
    assert abs((small[0].value or 0) + (small[1].value or 0)) < 1e-9


def test_ca405_vacio_no_es_cero() -> None:
    rows = [duel(1, 2)] * 10 + [duel(2, 1)] * 5
    result = fits.fit_dimension("x", rows, [1, 2, 9], params(), rng())
    empty = result.estimates[9]
    assert (empty.value, empty.low, empty.high, empty.n, empty.support) == (
        None,
        None,
        None,
        0,
        support.INSUFFICIENT,
    )
    assert writers.number(empty.value, 3) == ""


def test_el_unknown_rate_se_pondera_y_no_cuenta_en_n() -> None:
    rows = [duel(1, 2)] * 4
    rows.append(
        row(
            QuestionType.PAIRWISE_DIMENSION,
            {"choice": "unknown"},
            2.0,
            champion_a=1,
            champion_b=2,
            dimension_id=1,
        )
    )
    result = fits.fit_dimension("x", rows, [1, 2], params(), rng())
    assert result.unknown_rate[1] == pytest.approx(2.0 / 6.0)
    assert result.estimates[1].n == 4


def test_ca404_toda_estimacion_lleva_intervalo() -> None:
    rows = [duel(a, b) for a, b in itertools.permutations(range(1, 6), 2) for _ in range(6)]
    rows += [duel(1, 5)] * 10
    result = fits.fit_dimension("x", rows, list(range(1, 6)), params(), rng())
    for estimate in result.estimates.values():
        assert estimate.low is not None and estimate.high is not None and estimate.value is not None
        assert estimate.low <= estimate.value <= estimate.high


def test_un_remuestreo_que_parte_el_grafo_se_detecta() -> None:
    labels = graph.components(3, np.array([0, 1]), np.array([1, 2]))
    active = np.ones(3, dtype=bool)
    assert graph.preserved(labels, active, np.array([0, 1]), np.array([1, 2]))
    assert not graph.preserved(labels, active, np.array([0]), np.array([1]))


# ----------------------------------------------------------------------- ordinal y duplas


def lane(a: int, b: int, choice: str) -> Row:
    return row(
        QuestionType.LANE_MATCHUP, {"choice": choice}, champion_a=a, champion_b=b, role="mid"
    )


def test_el_matchup_es_antisimetrico_y_vale_cero_en_el_empate() -> None:
    z = np.log(np.array([0.6, 1.2]))
    assert ordinal.advantage(np.array([0.0]), z)[0] == pytest.approx(0.0, abs=1e-12)
    pos = ordinal.advantage(np.array([1.3]), z)[0]
    neg = ordinal.advantage(np.array([-1.3]), z)[0]
    assert pos == pytest.approx(-neg)
    assert 0 < pos < 1


def test_ca406_un_par_nunca_preguntado_es_prediccion() -> None:
    rows = [lane(1, 2, "a_strong")] * 12 + [lane(2, 3, "a_slight")] * 12 + [lane(1, 3, "even")] * 2
    rows += [lane(3, 4, "b_slight")] * 10
    roles = {c: ("mid",) for c in range(1, 5)}
    result = fits.fit_lane("mid", rows, [1, 2, 3, 4], roles, params(), rng())
    by_pair = {(m.a, m.b): m for m in result.matchups}
    unseen = by_pair[(1, 4)]
    seen = by_pair[(1, 2)]
    assert not unseen.observed and unseen.advantage.n == 0
    assert seen.observed and seen.advantage.n == 12
    assert seen.advantage.value is not None and seen.advantage.value > 0
    width = lambda e: (e.high or 0) - (e.low or 0)  # noqa: E731
    assert width(unseen.advantage) > width(seen.advantage)


def test_todos_even_dan_un_matchup_parejo() -> None:
    rows = [lane(1, 2, "even")] * 20
    result = fits.fit_lane("mid", rows, [1, 2], {1: ("mid",), 2: ("mid",)}, params(), rng())
    assert result.matchups[0].advantage.value == pytest.approx(0.0, abs=0.05)


def test_el_campeon_sin_el_rol_queda_vacio_aunque_tenga_respuestas() -> None:
    rows = [lane(1, 2, "a_slight")] * 10
    result = fits.fit_lane("mid", rows, [1, 2], {1: ("mid",), 2: ("top",)}, params(), rng())
    assert result.estimates[2].value is None


def duo_row(top: tuple[int, int], bottom: tuple[int, int], choice: str) -> Row:
    return row(
        QuestionType.DUO_SYNERGY,
        {"choice": choice},
        champion_a=top[0],
        champion_b=top[1],
        champion_c=bottom[0],
        champion_d=bottom[1],
        duo_ctx="bot",
        role_a="adc",
        role_b="support",
        role_c="adc",
        role_d="support",
    )


def test_la_dupla_no_observada_es_la_suma_de_sus_integrantes() -> None:
    """§5.4: `i = 0` por construcción; la fila dice `is_observed = false` y `_n = 0`."""
    rows = [duo_row((1, 2), (3, 4), "pair_1")] * 10 + [duo_row((1, 4), (3, 2), "similar")] * 8
    rows += [duo_row((1, 5), (3, 4), "pair_2")] * 6
    roles = {1: ("adc",), 3: ("adc",), 2: ("support",), 4: ("support",), 5: ("support",)}
    result = fits.fit_duos(
        "bot", "synergy", ("adc", "support"), rows, [1, 2, 3, 4, 5], roles, params(), rng()
    )
    # La dupla 3 + 5 nunca se preguntó: su valor es predicción del modelo.
    unseen = result.rows[fits.duo_key((3, "adc"), (5, "support"))]
    assert not unseen.observed and unseen.estimate.n == 0
    assert unseen.estimate.value is not None
    assert result.rows[fits.duo_key((1, "adc"), (2, "support"))].estimate.n == 10


def test_un_contexto_sin_respuestas_no_emite_filas() -> None:
    result = fits.fit_duos(
        "mid_jungle", "synergy", ("mid", "jungle"), [], [1, 2], {}, params(), rng()
    )
    assert result.rows == {}


# ------------------------------------------------------------------- pico y atributos


def test_la_mediana_ponderada_promedia_en_el_borde() -> None:
    assert simple.weighted_median([10, 20], [1, 1]) == 15
    assert simple.weighted_median([10, 20, 30], [1, 1, 5]) == 30
    assert simple.round_half_up(26.5) == 27


def test_la_curva_es_recalculable_desde_el_pico_de_la_fila() -> None:
    rows = [row(QuestionType.PEAK_TIMING, {"minute": m}, champion_a=1) for m in (18, 20, 22)]
    result = fits.fit_peaks(rows, [1], params(), rng())
    peak = int(result.estimates[1].value or 0)
    p = params()
    lines = writers.peak_rows(result, [1], {1: _info(1)}, p)
    power_15 = float(lines[0][writers.HEADERS["peak_timing"].index("power_at_15")])
    assert power_15 == pytest.approx(math.exp(-((15 - peak) ** 2) / (2 * 7.5**2)), abs=0.005)


def test_wilson_usa_el_tamano_efectivo() -> None:
    """§5.6: con pesos desiguales el intervalo es más ancho que con el conteo."""
    weights = [1.0, 1.0, 1.0, 0.1, 0.1, 0.1, 0.1, 0.1]
    n_eff = simple.kish(weights)
    assert n_eff < len(weights)
    low_eff, high_eff = simple.wilson(0.5, n_eff)
    low_n, high_n = simple.wilson(0.5, len(weights))
    assert high_eff - low_eff > high_n - low_n


def test_los_atributos_son_proporciones_ponderadas() -> None:
    rows = [
        row(QuestionType.TRAIT_MULTISELECT, {"traits": ["engage"]}, 3.0, champion_a=1),
        row(QuestionType.TRAIT_MULTISELECT, {"traits": ["poke"]}, 1.0, champion_a=1),
    ]
    result = fits.fit_traits(rows, [1, 2], ["engage", "poke"], params())
    assert result.estimates[(1, "engage")].value == pytest.approx(0.75)
    assert result.estimates[(1, "engage")].n == 2
    assert result.estimates[(2, "engage")].value is None


# ------------------------------------------------------------- formato y parámetros


def _info(champion_id: int) -> Any:
    from aggregation.load import ChampionInfo

    return ChampionInfo(champion_id, f"K{champion_id}", f"Champ {champion_id}", ("mid",), 1)


@pytest.mark.parametrize("kind", writers.KINDS)
def test_la_cabecera_es_la_del_fixture(kind: str) -> None:
    """26 §1: los ejemplos de `docs/examples/` son el fixture contra el que se comparan."""
    [path] = sorted(EXAMPLES.glob(f"{kind}_v*.csv"))
    with path.open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert writers.HEADERS[kind] == header


def test_el_formato_numerico_es_el_de_la_tabla() -> None:
    assert writers.number(-0.18, 3) == "-0.180"
    # Un valor que redondea a cero no lleva signo (§4.6, nota del 13/11/2026).
    assert writers.number(-0.0004, 3) == "0.000"
    assert writers.number(-0.004, 2) == "0.00"
    assert writers.number(-0.0005001, 3) == "-0.001"
    assert writers.number(0.34, 2) == "0.34"
    assert writers.number(None, 3) == ""
    assert writers.boolean(False) == "false"


def test_la_semilla_sale_de_los_parametros() -> None:
    """§4.2: los mismos parámetros dan la misma semilla, escritos como sean."""
    assert params(min_trust=Decimal("0.3")).seed == params(min_trust=Decimal("0.300")).seed
    assert params().seed != params(sigma=8.0).seed
    assert parse_window("16.18..16.20") == ("16.18", "16.20")
    assert parse_window("16.17") == ("16.17", "16.17")
