"""El job `check_graph_connectivity` — ADR-008 con la forma de ADR-021.

Lo que importa probar es la cota: el job materializa puentes, y si los materializara sin límite
sería la precomputación que prohíbe RF-111.
"""

from __future__ import annotations

import random
import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Champion, Dimension, Patch, Question, QuestionType, Respondent
from app.services import connectivity, sessions
from app.services.connectivity import UnionFind
from tests.conftest import (
    add_response,
    make_champions,
    make_dimensions,
    pairwise_question,
    requires_db,
    restrict_pool,
)


def test_union_find_agrupa_y_no_depende_del_orden() -> None:
    graph = UnionFind([5, 1, 3, 2, 4])
    assert graph.union(5, 3) is True
    assert graph.union(3, 5) is False
    graph.union(1, 2)
    assert graph.groups() == [[1, 2], [3, 5], [4]]


async def _bridges(db: AsyncSession, patch: Patch) -> list[Question]:
    return list(
        (
            await db.execute(
                sa.select(Question)
                .where(Question.patch_id == patch.patch_id, Question.bridge_priority)
                .order_by(Question.question_id)
            )
        ).scalars()
    )


async def _someone(db: AsyncSession, trust: str = "0.500") -> Respondent:
    row, _ = await sessions.create(db, f"huella-grafo-{uuid.uuid4()}")
    row.trust_score = Decimal(trust)
    await db.commit()
    return row


async def _run(db: AsyncSession) -> connectivity.DimensionReport:
    result = await connectivity.check(db, random.Random(8))
    [report] = result.dimensions
    return report


@requires_db
async def test_en_frio_se_materializan_k_menos_1_puentes(
    db: AsyncSession, patch: Patch, champions: list[Champion], dimension: Dimension
) -> None:
    """Cuatro campeones sin comparaciones son cuatro componentes: tres puentes, no seis pares."""
    await restrict_pool(db, champions, [dimension])

    report = await _run(db)

    bridges = await _bridges(db, patch)
    assert (report.components, report.marked, report.bridges) == (4, 3, 3)
    assert len(bridges) == 3
    assert all(q.type is QuestionType.PAIRWISE_DIMENSION for q in bridges)
    assert all(q.dimension_id == dimension.dimension_id for q in bridges)


@requires_db
async def test_una_segunda_corrida_no_agrega_puentes(
    db: AsyncSession, patch: Patch, champions: list[Champion], dimension: Dimension
) -> None:
    """Los puentes marcados que siguen haciendo falta cuentan como aristas tentativas."""
    await restrict_pool(db, champions, [dimension])
    await _run(db)

    again = await _run(db)

    assert (again.marked, again.cleared, again.bridges) == (0, 0, 3)
    assert len(await _bridges(db, patch)) == 3


@requires_db
async def test_un_puente_contestado_se_desmarca(
    db: AsyncSession, patch: Patch, champions: list[Champion], dimension: Dimension
) -> None:
    await restrict_pool(db, champions, [dimension])
    await _run(db)
    first = (await _bridges(db, patch))[0]
    await add_response(db, await _someone(db), first, {"choice": "a"})

    report = await _run(db)

    remaining = await _bridges(db, patch)
    assert report.components == 3
    assert (report.cleared, report.marked) == (1, 0)
    assert first.question_id not in {q.question_id for q in remaining}
    assert len(remaining) == 2


@requires_db
async def test_unknown_y_trust_bajo_no_conectan(
    db: AsyncSession, patch: Patch, champions: list[Champion], dimension: Dimension
) -> None:
    """Las aristas son las respuestas que entrarían a la agregación (25 §1)."""
    await restrict_pool(db, champions, [dimension])
    await _run(db)
    first, second, _ = await _bridges(db, patch)
    await add_response(db, await _someone(db), first, {"choice": "unknown"})
    await add_response(db, await _someone(db, trust="0.200"), second, {"choice": "b"})

    report = await _run(db)

    assert report.components == 4
    assert (report.cleared, report.bridges) == (0, 3)


@requires_db
async def test_nunca_marca_una_honeypot_como_puente(db: AsyncSession, patch: Patch) -> None:
    champions = await make_champions(db, patch, 2, prefix="Gr")
    [dimension] = await make_dimensions(db, ["grdim"])
    await restrict_pool(db, champions, [dimension])
    await pairwise_question(
        db,
        patch,
        champions[0],
        champions[1],
        dimension,
        is_honeypot=True,
        expected_answer={"choice": "a"},
    )

    report = await _run(db)

    assert (report.components, report.marked) == (2, 0)
    assert await _bridges(db, patch) == []


@requires_db
async def test_los_puentes_de_una_dimension_inactiva_se_desmarcan(
    db: AsyncSession, patch: Patch, champions: list[Champion], dimension: Dimension
) -> None:
    [other] = await make_dimensions(db, ["grotra"])
    await restrict_pool(db, champions, [dimension, other])
    await connectivity.check(db, random.Random(1))
    assert len(await _bridges(db, patch)) == 6

    await restrict_pool(db, champions, [dimension])
    result = await connectivity.check(db, random.Random(1))

    bridges = await _bridges(db, patch)
    assert len(bridges) == 3
    assert {q.dimension_id for q in bridges} == {dimension.dimension_id}
    assert result.connected == 0


def test_una_honeypot_entre_dos_campeones_sueltos_no_le_quita_un_puente() -> None:
    """En frío cada componente es un campeón: volver a sortear el par no alcanza, hay que cambiar
    de componente. Con cuatro componentes tiene que haber tres puentes, cualquiera sea el orden."""
    groups = [[1], [2], [3], [4]]
    avoid: set[tuple[int, int | None, int | None]] = {(1, 2, 7), (2, 3, 7), (3, 4, 7)}
    for seed in range(200):
        chain = connectivity._chain(groups, 7, avoid, random.Random(seed))
        pairs = {(c.champion_a, c.champion_b) for c in chain}
        assert len(chain) == 3, seed
        assert not pairs & {(1, 2), (2, 3), (3, 4)}
        graph = UnionFind([1, 2, 3, 4])
        for a, b in pairs:
            assert b is not None
            graph.union(a, b)
        assert graph.groups() == [[1, 2, 3, 4]]
