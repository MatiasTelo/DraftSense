"""Los textos de las preguntas que no salen de un catálogo (ADR-018).

El tipo 1 lee su enunciado y su definición de `dimensions`, y el tipo 5 la etiqueta y la
definición de cada atributo de `traits`, porque agregar una fila a esos catálogos no puede exigir
código (RF-603). El resto vive acá: la instrucción del ranking, los tipos 2, 3 y 4, que miden un
único concepto fijo, y el enunciado del tipo 5. El servidor los compone antes de enviarlos
(`docs/12-api.md` §1.1).

Desde la semana 8 cada texto existe en inglés y en español, y la pregunta se arma en el idioma que
pide el cliente con `lang` ([ADR-028]). Los términos del juego —engage, poke, power spike, bot
lane— quedan en inglés también en el texto en español (ADR-010).

Cambiar uno de estos textos cambia lo que la gente contesta. No es un retoque de estilo: tiene
que quedar en el historial y, si altera el significado, en la documentación.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from app.models import DuoContext
from app.services.answers import PEAK_MAX_MINUTE, PEAK_MIN_MINUTE

Lang = Literal["en", "es"]
LANGS: Final[tuple[Lang, ...]] = ("en", "es")
DEFAULT_LANG: Final[Lang] = "en"

#: Los extremos se importan de la validación del `answer`: la escala que se muestra y la que se
#: acepta no pueden divergir sin que el cliente ofrezca minutos que el servidor rechaza.
PEAK_MIN: Final = PEAK_MIN_MINUTE
PEAK_MAX: Final = PEAK_MAX_MINUTE
PEAK_STEP: Final = 1
#: El centro de la escala. No es una posición neutra útil a propósito: quien confirma sin mover
#: el slider queda delatado por un `response_time_ms` bajo (§3).
PEAK_DEFAULT: Final = 20


@dataclass(frozen=True, slots=True)
class Texts:
    """Todos los textos fijos de un idioma. Los dos idiomas tienen exactamente los mismos campos y
    los mismos marcadores de sustitución: lo verifica `tests/test_questions.py`."""

    #: La opción de escape del tipo 1. El «no sé» es información real —alimenta `unknown_rate`—
    #: y por eso es una opción explícita y no la ausencia de respuesta. Desde ADR-022 vale para el
    #: ranking entero.
    unknown_label: str
    #: La segunda línea del tipo 1: cómo se contesta un ranking (`20-tipos-de-pregunta.md` §2).
    ranking_instruction: str

    # Tipo 2: pico de poder (20 §3).
    peak_prompt: str
    peak_help_label: str
    peak_help_text: str
    peak_unit: str
    peak_marks: tuple[tuple[int, str], ...]

    # Tipo 3, variante 1v1 (20 §4.1). Una plantilla por nivel, en el orden en que se muestran:
    # los botones llevan el nombre del campeón y no «A» y «B» (CA-104).
    lane_prompt: str
    lane_help_label: str
    #: Sin esta aclaración cada persona contesta sobre un escenario distinto.
    lane_help_text: str
    lane_option_templates: dict[str, str]

    # Tipo 3, variante 2v2 (20 §4.2, 12 §2.3). La dupla de arriba es `a`.
    bot_prompt: str
    bot_help_label: str
    #: La segunda frase lo separa del tipo 4, que se ve parecido y mide otra cosa.
    bot_help_text: str
    bot_option_labels: dict[str, str]

    # Tipo 4: sinergia (20 §5). Las opciones en el orden en que se muestran.
    duo_prompt: str
    duo_help_label: str
    duo_help_text: str
    duo_option_labels: dict[str, str]
    #: La etiqueta del contexto de una dupla, sobre la tarjeta (12 §2.3, nota del 29/10).
    duo_context_labels: dict[DuoContext, str]

    # Tipo 5: atributos (20 §6). Cada atributo trae su etiqueta y su definición de `traits`.
    traits_prompt: str
    traits_subtitle: str


EN: Final = Texts(
    unknown_label="Not sure",
    ranking_instruction="Drag to order: most at the top.",
    peak_prompt="When does {name} peak?",
    peak_help_label="Power spike",
    peak_help_text=(
        "The point in the game where this champion is at their strongest compared to everyone "
        "else."
    ),
    peak_unit="min",
    peak_marks=((0, "laning"), (15, "mid game"), (30, "late game")),
    lane_prompt="Who wins this lane at 10 minutes?",
    lane_help_label="Lane matchup",
    lane_help_text="Assume equal skill and no jungle interference.",
    lane_option_templates={
        "a_strong": "{a} wins hard",
        "a_slight": "{a} wins slightly",
        "even": "Even",
        "b_slight": "{b} wins slightly",
        "b_strong": "{b} wins hard",
    },
    bot_prompt="Which bot lane wins at 10 minutes?",
    bot_help_label="Bot lane matchup",
    bot_help_text=(
        "Which pair beats the other in lane. Not about how well each pair works together — "
        "that's a different question."
    ),
    bot_option_labels={
        "a_strong": "Top pair wins hard",
        "a_slight": "Top pair wins slightly",
        "even": "Even",
        "b_slight": "Bottom pair wins slightly",
        "b_strong": "Bottom pair wins hard",
    },
    duo_prompt="Which duo works better together?",
    duo_help_label="Synergy",
    duo_help_text="Ignore who they're up against. Which two complement each other better?",
    duo_option_labels={
        "pair_1": "Top pair",
        "similar": "About the same",
        "pair_2": "Bottom pair",
    },
    duo_context_labels={
        DuoContext.BOT: "BOT",
        DuoContext.TOP_JUNGLE: "TOP + JUNGLE",
        DuoContext.MID_JUNGLE: "MID + JUNGLE",
    },
    traits_prompt="What does {name} do well?",
    traits_subtitle="Pick all that apply.",
)

#: Aprobadas por el alumno el 29/10/2026: español neutro con «tú».
ES: Final = Texts(
    unknown_label="No estoy seguro",
    ranking_instruction="Arrastra para ordenar: el que más tiene, arriba.",
    peak_prompt="¿Cuándo tiene {name} su power spike?",
    peak_help_label="Power spike",
    peak_help_text=(
        "El momento de la partida en que este campeón está más fuerte en comparación con el resto."
    ),
    peak_unit="min",
    peak_marks=((0, "fase de líneas"), (15, "mid game"), (30, "late game")),
    lane_prompt="¿Quién gana esta línea al minuto 10?",
    lane_help_label="Enfrentamiento de línea",
    lane_help_text="Supón igual habilidad y sin intervención del jungla.",
    lane_option_templates={
        "a_strong": "{a} gana claramente",
        "a_slight": "{a} gana por poco",
        "even": "Parejo",
        "b_slight": "{b} gana por poco",
        "b_strong": "{b} gana claramente",
    },
    bot_prompt="¿Qué dupla gana la bot lane al minuto 10?",
    bot_help_label="Enfrentamiento de bot lane",
    bot_help_text=(
        "Qué dupla le gana a la otra en la línea. No se trata de qué tan bien se complementa cada "
        "dupla: esa es otra pregunta."
    ),
    bot_option_labels={
        "a_strong": "La dupla de arriba gana claramente",
        "a_slight": "La dupla de arriba gana por poco",
        "even": "Parejo",
        "b_slight": "La dupla de abajo gana por poco",
        "b_strong": "La dupla de abajo gana claramente",
    },
    duo_prompt="¿Qué dupla funciona mejor junta?",
    duo_help_label="Sinergia",
    duo_help_text="Ignora contra quién juegan. ¿Qué dos se complementan mejor?",
    duo_option_labels={
        "pair_1": "Dupla de arriba",
        "similar": "Más o menos igual",
        "pair_2": "Dupla de abajo",
    },
    duo_context_labels={
        DuoContext.BOT: "BOT",
        DuoContext.TOP_JUNGLE: "TOP + JUNGLA",
        DuoContext.MID_JUNGLE: "MID + JUNGLA",
    },
    traits_prompt="¿En qué se destaca {name}?",
    traits_subtitle="Elige todos los que correspondan.",
)

TEXTS: Final[dict[Lang, Texts]] = {"en": EN, "es": ES}


def texts(lang: Lang = DEFAULT_LANG) -> Texts:
    return TEXTS[lang]


# Los nombres de antes de la semana 8, en inglés, para quien los importa sueltos.
UNKNOWN_LABEL: Final = EN.unknown_label
RANKING_INSTRUCTION: Final = EN.ranking_instruction
LANE_OPTION_TEMPLATES: Final = EN.lane_option_templates
