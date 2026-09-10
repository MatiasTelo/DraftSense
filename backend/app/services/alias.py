"""Generación del alias público.

Forma `adjetivo-sustantivo-NNNN` (`docs/23-gamificacion.md` §4). **No se deriva del
`respondent_id` ni de la huella**: se sortea. Que no sea derivable es el requisito (CA-312), no
un detalle de implementación, así que la fuente de aleatoriedad es `secrets` y no un hash de nada.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

import yaml

SEEDS_DIR = Path(__file__).resolve().parents[3] / "infra" / "seeds"


@lru_cache
def _words() -> tuple[tuple[str, ...], tuple[str, ...]]:
    data = yaml.safe_load((SEEDS_DIR / "alias_words.yaml").read_text(encoding="utf-8"))
    return tuple(data["adjectives"]), tuple(data["nouns"])


def generate_alias() -> str:
    adjectives, nouns = _words()
    return (
        f"{secrets.choice(adjectives)}-{secrets.choice(nouns)}-{secrets.randbelow(10000):04d}"
    )
