"""El job `check_graph_connectivity` (ADR-008, con la forma de ADR-021).

Bradley-Terry necesita que el grafo de comparaciones de cada dimensión esté conectado: dos grupos
de campeones que nunca se compararon no tienen un orden relativo, y el ajuste no tiene solución
única. Nada en la función de prioridad lo garantiza, así que este job busca las componentes y
**materializa los puentes** que las unirían, marcados con `bridge_priority` para que el sampler
los sirva primero.

Las preguntas no existen hasta que se sirven (RF-111), así que marcar puentes es crearlos. Para no
precomputar, el job mantiene como mucho k-1 puentes válidos por dimensión: una cadena entre
componentes en orden aleatorio, que trata igual a todas (ADR-021).
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Question, QuestionType, Response
from app.services import aggregable, honeypots, questions
from app.services.questions import Combination

PAIRWISE: Final = QuestionType.PAIRWISE_DIMENSION
DECISIVE: Final = ("a", "b")

#: Cuántas veces se vuelve a sortear un par que cayó sobre una honeypot antes de rendirse.
HONEYPOT_REDRAWS: Final = 10


class UnionFind:
    """Componentes conexas con unión por raíz menor, para que el resultado no dependa del orden."""

    def __init__(self, items: Iterable[int]) -> None:
        self._parent = {item: item for item in items}

    def find(self, item: int) -> int:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: int, b: int) -> bool:
        """Une las componentes de `a` y `b`. Devuelve `False` si ya eran la misma."""
        root_a, root_b = self.find(a), self.find(b)
        if root_a == root_b:
            return False
        low, high = sorted((root_a, root_b))
        self._parent[high] = low
        return True

    def groups(self) -> list[list[int]]:
        members: dict[int, list[int]] = defaultdict(list)
        for item in sorted(self._parent):
            members[self.find(item)].append(item)
        return [members[root] for root in sorted(members)]


@dataclass(frozen=True, slots=True)
class DimensionReport:
    code: str
    components: int
    bridges: int
    marked: int
    cleared: int


@dataclass(frozen=True, slots=True)
class ConnectivityResult:
    patch: str | None
    dimensions: list[DimensionReport] = field(default_factory=list)

    @property
    def connected(self) -> int:
        """Dimensiones con el grafo conectado: el número que pide 21 §7.2."""
        return sum(1 for d in self.dimensions if d.components <= 1)


async def _edges(
    session: AsyncSession, patch_id: int
) -> dict[int, set[tuple[int, int]]]:
    """Los pares comparados con una respuesta decisiva que entraría a la agregación."""
    threshold = await aggregable.min_trust(session)
    rows = await session.execute(
        sa.select(Question.dimension_id, Question.champion_a, Question.champion_b)
        .select_from(aggregable.source())
        .where(
            Question.patch_id == patch_id,
            Question.type == PAIRWISE,
            Response.answer["choice"].astext.in_(DECISIVE),
            *aggregable.conditions(threshold),
        )
        .distinct()
    )
    edges: dict[int, set[tuple[int, int]]] = defaultdict(set)
    for dimension_id, a, b in rows.tuples():
        if dimension_id is not None and b is not None:
            edges[dimension_id].add((a, b))
    return edges


def _pair(
    left: list[int],
    right: list[int],
    dimension_id: int,
    avoid: set[tuple[int, int | None, int | None]],
    rng: random.Random,
) -> Combination | None:
    """Un par al azar entre dos componentes que no sea una honeypot, o `None` si no lo encuentra."""
    for _ in range(HONEYPOT_REDRAWS):
        low, high = sorted((rng.choice(left), rng.choice(right)))
        if (low, high, dimension_id) not in avoid:
            return Combination(PAIRWISE, low, champion_b=high, dimension_id=dimension_id)
    return None


def _chain(
    groups: list[list[int]],
    dimension_id: int,
    avoid: set[tuple[int, int | None, int | None]],
    rng: random.Random,
) -> list[Combination]:
    """Los puentes de una cadena en orden aleatorio entre las componentes (ADR-021).

    Si el par entre una componente y la siguiente es una honeypot y no se puede volver a sortear
    —en frío las dos son un solo campeón y el sorteo da siempre el mismo par—, la cadena sigue con
    la próxima componente del orden que sí se pueda unir. Si la actual no se une con ninguna de las
    que faltan, la próxima se engancha a una componente anterior de la cadena. Sin esto, cada
    honeypot del catálogo podía dejar a su dimensión sin un puente.
    """
    remaining = list(groups)
    rng.shuffle(remaining)
    if not remaining:
        return []

    def attach(anchor: list[int]) -> tuple[int, Combination] | None:
        for index, candidate in enumerate(remaining):
            bridge = _pair(anchor, candidate, dimension_id, avoid, rng)
            if bridge is not None:
                return index, bridge
        return None

    current = remaining.pop(0)
    placed = [current]
    chain: list[Combination] = []
    while remaining:
        found = attach(current)
        if found is None:
            for anchor in rng.sample(placed, len(placed)):
                found = attach(anchor)
                if found is not None:
                    break
        if found is None:
            # Nada de lo que falta se une a la cadena sin caer en una honeypot: la próxima corrida
            # vuelve a barajar.
            break
        index, bridge = found
        chain.append(bridge)
        current = remaining.pop(index)
        placed.append(current)
    return chain


async def check(session: AsyncSession, rng: random.Random | None = None) -> ConnectivityResult:
    """Recalcula las componentes de cada dimensión activa y ajusta los puentes. Hace commit."""
    rng = rng or random.Random()
    patch = await questions.current_patch(session)
    if patch is None:
        return ConnectivityResult(patch=None)

    space = await questions.load_space(session)
    enabled = space.champion_ids
    edges = await _edges(session, patch.patch_id)
    marked_rows = (
        await session.execute(
            sa.select(Question)
            .where(
                Question.patch_id == patch.patch_id,
                Question.bridge_priority,
                Question.type == PAIRWISE,
            )
            .order_by(Question.question_id)
        )
    ).scalars()
    bridges: dict[int | None, list[Question]] = defaultdict(list)
    for question in marked_rows:
        bridges[question.dimension_id].append(question)
    avoid = {
        (q.champion_a, q.champion_b, q.dimension_id)
        for q in await honeypots.catalog(session, patch.patch_id)
    }

    to_clear: list[int] = []
    to_mark: list[Combination] = []
    reports: list[DimensionReport] = []
    for dimension in space.dimensions:
        did = dimension.dimension_id
        graph = UnionFind(enabled)
        for a, b in edges.get(did, ()):
            if a in enabled and b in enabled:
                graph.union(a, b)
        components = len(graph.groups())

        # Los puentes marcados que todavía unen componentes cuentan como aristas tentativas: se
        # van a contestar. Los que ya no unen nada —o repiten lo que une otro— se desmarcan.
        kept = 0
        cleared = 0
        for bridge in bridges.pop(did, []):
            first, second = bridge.champion_a, bridge.champion_b
            if (
                second is not None
                and first in enabled
                and second in enabled
                and graph.union(first, second)
            ):
                kept += 1
            else:
                to_clear.append(bridge.question_id)
                cleared += 1

        new = _chain(graph.groups(), did, avoid, rng)
        to_mark.extend(new)
        reports.append(
            DimensionReport(
                code=dimension.code,
                components=components,
                bridges=kept + len(new),
                marked=len(new),
                cleared=cleared,
            )
        )

    # Los puentes de dimensiones que ya no están activas no se van a servir: se desmarcan.
    for leftover in bridges.values():
        to_clear.extend(q.question_id for q in leftover)

    if to_clear:
        await session.execute(
            sa.update(Question)
            .where(Question.question_id.in_(to_clear))
            .values(bridge_priority=False)
            .execution_options(synchronize_session="fetch")
        )
    created = await questions.materialize_many(session, patch.patch_id, to_mark)
    if created:
        await session.execute(
            sa.update(Question)
            .where(Question.question_id.in_([q.question_id for q in created.values()]))
            .values(bridge_priority=True)
            .execution_options(synchronize_session="fetch")
        )
    await session.commit()
    return ConnectivityResult(patch=patch.version, dimensions=reports)
