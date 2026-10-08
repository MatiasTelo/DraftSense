"""Carga del catálogo de honeypots desde `infra/seeds/honeypots_<parche>.yaml` (22 §3.3).

Cada entrada es un par de campeones, una dimensión, la respuesta esperada y el `rationale`: el hecho
del kit que la sostiene (ADR-013). El `rationale` no se guarda en la base —no hay columna para
eso—, pero es obligatorio en el archivo: es la mitad del mecanismo, lo que permite que cualquiera
audite la respuesta esperada sin apelar a la autoridad de quien la escribió.

La carga es **conservadora** (nota del 16/09 en 22 §3.3):

- es idempotente: correrla dos veces no cambia nada;
- no reactiva una honeypot que el monitoreo retiró, salvo con `force`;
- no convierte en honeypot una pregunta que ya tiene respuestas comunes;
- no cambia la respuesta esperada de una honeypot vigente.

Lo que saltea lo informa, para que la decisión la tome una persona.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import sqlalchemy as sa
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Champion, Dimension, Question, QuestionType, Response
from app.seeds.catalog import SEEDS_DIR
from app.services.honeypots import ELIGIBLE_DIMENSIONS
from app.services.questions import Combination, identity

REQUIRED_FIELDS: Final = frozenset(
    {"champion_a", "champion_b", "dimension", "expected", "rationale"}
)
EXPECTED_CHOICES: Final = ("a", "b")
FLIPPED: Final = {"a": "b", "b": "a"}

#: Sólo el núcleo del pool: una honeypot con un campeón que nunca aparece se delataría.
HONEYPOT_TIER: Final = 1


def honeypot_path(patch: str, seeds_dir: Path | None = None) -> Path:
    return (seeds_dir or SEEDS_DIR) / f"honeypots_{patch}.yaml"


def load_honeypots(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} debe contener una lista de entradas")
    return data


def validate_honeypots(entries: list[dict[str, Any]]) -> list[str]:
    """Errores de forma del catálogo, para fallar antes de tocar la base."""
    problems: list[str] = []
    seen: set[tuple[frozenset[str], str]] = set()
    for index, entry in enumerate(entries):
        where = f"entrada {index}"
        missing = REQUIRED_FIELDS - set(entry)
        if missing:
            problems.append(f"{where}: faltan campos {sorted(missing)}")
            continue
        a, b, dimension = entry["champion_a"], entry["champion_b"], entry["dimension"]
        where = f"entrada {index} ({a} / {b}, {dimension})"
        if a == b:
            problems.append(f"{where}: los dos campeones son el mismo")
        if dimension not in ELIGIBLE_DIMENSIONS:
            problems.append(
                f"{where}: la dimensión no admite honeypots (ADR-013 admite "
                f"{', '.join(sorted(ELIGIBLE_DIMENSIONS))})"
            )
        expected = entry["expected"]
        if not isinstance(expected, dict) or set(expected) != {"choice"} or (
            expected["choice"] not in EXPECTED_CHOICES
        ):
            problems.append(f"{where}: expected tiene que ser {{choice: a}} o {{choice: b}}")
        rationale = entry["rationale"]
        if not isinstance(rationale, str) or not rationale.strip():
            problems.append(f"{where}: el rationale es obligatorio (22 §3.3)")
        key = (frozenset({str(a), str(b)}), str(dimension))
        if key in seen:
            problems.append(f"{where}: par repetido")
        seen.add(key)
    return problems


@dataclass(slots=True)
class SeedHoneypotsResult:
    created: int = 0
    converted: int = 0
    reactivated: int = 0
    unchanged: int = 0
    skipped: list[str] = field(default_factory=list)


class HoneypotCatalogError(ValueError):
    """El catálogo nombra algo que la base no tiene, o un campeón fuera del núcleo."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


async def _champions_by_name(session: AsyncSession) -> dict[str, Champion]:
    """Cada campeón por su nombre visible, su nombre de Riot y su clave: vale cualquiera."""
    names: dict[str, Champion] = {}
    for champion in (await session.execute(sa.select(Champion))).scalars():
        for name in (champion.display_name, champion.riot_name, champion.riot_key):
            names.setdefault(name, champion)
    return names


async def seed_honeypots(
    session: AsyncSession,
    patch_id: int,
    entries: list[dict[str, Any]],
    *,
    force: bool = False,
) -> SeedHoneypotsResult:
    """Carga el catálogo en el parche. Valida todo antes de escribir la primera fila."""
    champions = await _champions_by_name(session)
    dimensions = {
        d.code: d for d in (await session.execute(sa.select(Dimension))).scalars()
    }

    problems: list[str] = []
    resolved: list[tuple[str, Combination, dict[str, str]]] = []
    for entry in entries:
        label = f"{entry['champion_a']} / {entry['champion_b']} ({entry['dimension']})"
        a = champions.get(entry["champion_a"])
        b = champions.get(entry["champion_b"])
        dimension = dimensions.get(entry["dimension"])
        for name, champion in ((entry["champion_a"], a), (entry["champion_b"], b)):
            if champion is None:
                problems.append(f"{label}: no existe el campeón {name}")
            elif champion.pool_tier != HONEYPOT_TIER:
                problems.append(f"{label}: {name} no es de tier {HONEYPOT_TIER}")
        if dimension is None:
            problems.append(f"{label}: no existe la dimensión")
        if a is None or b is None or dimension is None:
            continue
        choice = str(entry["expected"]["choice"])
        # Forma canónica: `questions_canonical_order` exige champion_a < champion_b. Si el
        # archivo los tiene al revés, la respuesta esperada se invierte con ellos.
        if a.champion_id > b.champion_id:
            a, b = b, a
            choice = FLIPPED[choice]
        combination = Combination(
            QuestionType.PAIRWISE_DIMENSION,
            a.champion_id,
            champion_b=b.champion_id,
            dimension_id=dimension.dimension_id,
        )
        resolved.append((label, combination, {"choice": choice}))
    if problems:
        raise HoneypotCatalogError(problems)

    result = SeedHoneypotsResult()
    for label, combination, expected in resolved:
        existing = (
            await session.execute(sa.select(Question).where(*identity(combination, patch_id)))
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                Question(
                    type=combination.type,
                    patch_id=patch_id,
                    champion_a=combination.champion_a,
                    champion_b=combination.champion_b,
                    dimension_id=combination.dimension_id,
                    is_honeypot=True,
                    expected_answer=expected,
                )
            )
            result.created += 1
            continue

        if existing.is_honeypot:
            if existing.expected_answer == expected:
                result.unchanged += 1
            else:
                result.skipped.append(
                    f"{label}: ya es honeypot con otra respuesta esperada "
                    f"({existing.expected_answer}); no se cambia"
                )
            continue

        if existing.expected_answer is not None:
            # Tuvo respuesta esperada y ya no es honeypot: la retiró el monitoreo (22 §3.4).
            if force:
                existing.is_honeypot = True
                existing.expected_answer = expected
                result.reactivated += 1
            else:
                result.skipped.append(
                    f"{label}: la retiró el monitoreo de pass rate; --force para reactivarla"
                )
            continue

        answered = (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(Response)
                .where(Response.question_id == existing.question_id)
            )
        ).scalar_one()
        if answered:
            result.skipped.append(
                f"{label}: ya tiene {answered} respuestas como pregunta común; "
                "convertirla cambiaría datos que ya se dieron"
            )
            continue
        existing.is_honeypot = True
        existing.expected_answer = expected
        result.converted += 1

    await session.commit()
    return result
