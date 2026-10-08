"""La fórmula del trust score — `docs/22-calidad-de-datos.md` §7.1 y CA-302.

La tabla de valores de referencia de §7.1 es el contrato: si la fórmula cambia, estos números
cambian primero en el documento.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.trust import DEFAULT_PARAMS, Counters, TrustParams, compute


@pytest.mark.parametrize(
    ("counters", "expected"),
    [
        pytest.param(Counters(), "0.500", id="respondedor nuevo"),
        pytest.param(Counters(honeypot_attempts=1), "0.400", id="falla su primer honeypot"),
        pytest.param(
            Counters(honeypot_attempts=1, honeypot_passed=1), "0.600", id="pasa su primer honeypot"
        ),
        pytest.param(Counters(honeypot_attempts=5), "0.286", id="5 de 5 fallados"),
        pytest.param(
            Counters(
                honeypot_attempts=10,
                honeypot_passed=10,
                retest_pairs=10,
                retest_consistent=8,
                answers_count=200,
            ),
            "0.850",
            id="10/10 honeypots y 8/10 retests",
        ),
    ],
)
def test_los_valores_de_referencia_de_la_tabla(counters: Counters, expected: str) -> None:
    """§7.1, fila por fila. La primera es además el DEFAULT de la columna: coinciden por diseño."""
    assert compute(counters) == Decimal(expected)


def test_ca302_el_primer_honeypot_fallado_baja_el_trust_a_lo_que_dice_la_formula() -> None:
    before = compute(Counters(answers_count=12))
    after = compute(Counters(honeypot_attempts=1, answers_count=13))
    assert before == Decimal("0.500")
    assert after < before
    assert after == Decimal("0.400")


def test_cinco_fallos_cruzan_el_umbral_del_export() -> None:
    """§7.3 — cruzar 0.30 hacia abajo requiere fallar unas cinco honeypots, no es un accidente.

    Con cuatro el trust queda exactamente en 0.300, que el filtro `trust_score >= min_trust` todavía
    deja pasar.
    """
    assert compute(Counters(honeypot_attempts=4)) == Decimal("0.300")
    assert compute(Counters(honeypot_attempts=5)) < Decimal("0.30")


def test_el_piso_de_20_protege_a_quien_recien_empieza() -> None:
    """Dos apuradas en cinco respuestas: sin el piso, `d` valdría 0.4 y no 0.1."""
    assert compute(Counters(fast_answers=2, answers_count=5)) == Decimal("0.475")


def test_el_denominador_crece_con_el_volumen() -> None:
    """Con 200 respuestas el denominador es 30 (15 %), no 20."""
    assert compute(Counters(fast_answers=3, answers_count=200)) == Decimal("0.475")


def test_una_racha_pesa_como_dos_apuradas() -> None:
    assert compute(Counters(straightline_runs=1, answers_count=5)) == compute(
        Counters(fast_answers=2, answers_count=5)
    )


def test_el_descuento_satura_en_la_mitad() -> None:
    """`d` no pasa de 1, así que el patrón degenerado a lo sumo divide el trust por dos."""
    assert compute(Counters(fast_answers=400, answers_count=100)) == Decimal("0.250")


def test_el_resultado_queda_entre_cero_y_uno_con_cualquier_peso() -> None:
    generous = TrustParams(honeypot=1.0, retest=1.0, degenerate=0.0, smoothing=2)
    assert compute(Counters(honeypot_attempts=9, honeypot_passed=9), generous) == Decimal("1.000")
    harsh = TrustParams(honeypot=0.6, retest=0.4, degenerate=2.0, smoothing=2)
    assert compute(Counters(fast_answers=100, answers_count=20), harsh) == Decimal("0.000")


def test_los_parametros_por_defecto_son_los_del_documento() -> None:
    """§8 — si cambian acá, tiene que cambiar el seed de `app_settings` y el documento."""
    assert TrustParams(honeypot=0.60, retest=0.40, degenerate=0.50, smoothing=2) == DEFAULT_PARAMS
