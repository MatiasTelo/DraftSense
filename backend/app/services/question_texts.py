"""Los textos de las preguntas que no salen de un catálogo (ADR-018).

El tipo 1 lee su enunciado y su definición de `dimensions`, porque agregar una dimensión es
insertar una fila (RF-603). Los tipos 2 y 3 miden un único concepto fijo y no tienen tabla: sus
textos viven acá, y el servidor los compone antes de enviarlos (`docs/12-api.md` §1.1). Son el
texto literal que ve el usuario, en inglés (ADR-010); el español de la semana 8 entra en este
mismo módulo.

Cambiar uno de estos textos cambia lo que la gente contesta. No es un retoque de estilo: tiene
que quedar en el historial y, si altera el significado, en la documentación.
"""

from __future__ import annotations

from typing import Final

from app.services.answers import PEAK_MAX_MINUTE, PEAK_MIN_MINUTE

#: La opción de escape del tipo 1. El «no sé» es información real —alimenta `D_unknown_rate`—
#: y por eso es una opción explícita y no la ausencia de respuesta.
UNKNOWN_LABEL: Final = "Not sure"

# --- Tipo 2: pico de poder (`docs/20-tipos-de-pregunta.md` §3) ---------------------------------

PEAK_PROMPT: Final = "When does {name} peak?"
PEAK_HELP_LABEL: Final = "Power spike"
PEAK_HELP_TEXT: Final = (
    "The point in the game where this champion is at their strongest compared to everyone else."
)

#: Los extremos se importan de la validación del `answer`: la escala que se muestra y la que se
#: acepta no pueden divergir sin que el cliente ofrezca minutos que el servidor rechaza.
PEAK_MIN: Final = PEAK_MIN_MINUTE
PEAK_MAX: Final = PEAK_MAX_MINUTE
PEAK_STEP: Final = 1
#: El centro de la escala. No es una posición neutra útil a propósito: quien confirma sin mover
#: el slider queda delatado por un `response_time_ms` bajo (§3).
PEAK_DEFAULT: Final = 20
PEAK_UNIT: Final = "min"
PEAK_MARKS: Final = ((0, "laning"), (15, "mid game"), (30, "late game"))

# --- Tipo 3, variante 1v1: enfrentamiento de línea (§4.1) --------------------------------------

LANE_PROMPT: Final = "Who wins this lane at 10 minutes?"
LANE_HELP_LABEL: Final = "Lane matchup"
#: Sin esta aclaración cada persona contesta sobre un escenario distinto.
LANE_HELP_TEXT: Final = "Assume equal skill and no jungle interference."

#: Una plantilla por nivel, en el orden en que se muestran. Los botones llevan el nombre del
#: campeón y no «A» y «B»: elimina el paso mental de mapear letra a retrato (CA-104).
LANE_OPTION_TEMPLATES: Final[dict[str, str]] = {
    "a_strong": "{a} wins hard",
    "a_slight": "{a} wins slightly",
    "even": "Even",
    "b_slight": "{b} wins slightly",
    "b_strong": "{b} wins hard",
}
