"""Las métricas de CU-07 y los indicadores del tier 2 (CA-607, CA-608).

El escenario, con tres campeones y dos dimensiones habilitados:

| Pregunta | Quién | Respuesta | ¿Agregable? |
|---|---|---|---|
| A-B en `one` | r | `a` | sí |
| B-C en `one` | r | `b` | sí |
| A-B en `two` | r | `unknown` | sí, pero no es comparación decisiva |
| A-C en `two`, honeypot | r | `a` | no: honeypot |
| A-B en `one` | f (marcado) | `b` | no: marcado |

`D_n`: en `one`, A = 1, B = 2, C = 1; en `two`, todos 0. Mediana de las seis celdas: 0.5.
`one` queda conectada (A-B-C) y `two` partida en tres.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Champion, Dimension, Patch
from tests.conftest import (
    add_response,
    make_champions,
    make_dimensions,
    make_respondent,
    pairwise_question,
    requires_db,
    restrict_pool,
)

pytestmark = requires_db


@pytest.fixture
async def scenario(
    db: AsyncSession, patch: Patch
) -> tuple[list[Champion], list[Dimension]]:
    a, b, c = await make_champions(db, patch, 3, prefix="Stat")
    one, two = await make_dimensions(db, ["statone", "stattwo"])
    await restrict_pool(db, [a, b, c], [one, two])

    r = await make_respondent(db, "fp-r")
    f = await make_respondent(db, "fp-f")
    f.is_flagged = True
    await db.commit()

    ab_one = await pairwise_question(db, patch, a, b, one)
    bc_one = await pairwise_question(db, patch, b, c, one)
    ab_two = await pairwise_question(db, patch, a, b, two)
    honeypot = await pairwise_question(
        db, patch, a, c, two, is_honeypot=True, expected_answer={"choice": "a"}
    )
    await add_response(db, r, ab_one, {"choice": "a"})
    await add_response(db, r, bc_one, {"choice": "b"})
    await add_response(db, r, ab_two, {"choice": "unknown"})
    await add_response(db, r, honeypot, {"choice": "a"})
    await add_response(db, f, ab_one, {"choice": "b"})
    return [a, b, c], [one, two]


async def test_overview_counts_submissions_and_aggregable(
    client: AsyncClient, scenario: tuple[list[Champion], list[Dimension]], patch: Patch
) -> None:
    body = (await client.get("/overview", params={"days": 7})).json()
    assert body["patch"] == patch.version
    assert body["totals"] == {
        "submissions": 5,
        "rows": 5,
        "aggregable_rows": 3,
        "respondents": 2,
        "flagged_respondents": 1,
    }
    assert body["today_submissions"] == 5
    assert len(body["volume"]) == 7
    assert body["volume"][-1]["counts"]["pairwise_dimension"] == 5
    assert body["connected_dimensions"] == 1
    assert body["total_dimensions"] == 2


async def test_overview_rejects_other_windows(client: AsyncClient) -> None:
    response = await client.get("/overview", params={"days": 14})
    assert response.status_code == 400


async def test_connectivity_and_tier_indicators(
    client: AsyncClient, scenario: tuple[list[Champion], list[Dimension]]
) -> None:
    body = (await client.get("/connectivity")).json()
    by_code = {d["code"]: d for d in body["dimensions"]}
    assert by_code["statone"]["components"] == 1
    assert by_code["statone"]["connected"] is True
    assert by_code["stattwo"]["components"] == 3
    assert by_code["stattwo"]["largest_component"] == 1

    tier = body["tier"]
    assert tier["median_dn"] == 0.5
    assert tier["median_threshold"] == 25
    assert tier["connected"] == 1
    assert tier["connected_threshold"] == 6
    assert tier["meets_median"] is False
    assert tier["meets_connectivity"] is False
    assert tier["ready"] is False


async def test_coverage_excludes_honeypots_and_flagged(
    client: AsyncClient, scenario: tuple[list[Champion], list[Dimension]]
) -> None:
    (a, b, c), _ = scenario
    body = (await client.get("/coverage")).json()
    rows = {r["champion_id"]: r for r in body["champions"]}
    assert rows[a.champion_id]["counts"] == {"statone": 1, "stattwo": 0}
    assert rows[b.champion_id]["counts"] == {"statone": 2, "stattwo": 0}
    assert rows[c.champion_id]["counts"] == {"statone": 1, "stattwo": 0}
    assert body["bands"] == {"solid": 25, "limited": 10}
    # Ordenada por la `D_n` mínima: los tres tienen 0, así que desempata el nombre.
    assert [r["name"] for r in body["champions"]] == sorted(r["name"] for r in body["champions"])


async def test_quality_histogram_has_twenty_bins(
    client: AsyncClient, scenario: tuple[list[Champion], list[Dimension]]
) -> None:
    body = (await client.get("/quality")).json()
    assert len(body["histogram"]) == 20
    # Los dos respondedores arrancan en 0.500: caen en [0.50, 0.55).
    assert body["histogram"][10]["count"] == 2
    assert sum(b["count"] for b in body["histogram"]) == 2
    assert len(body["flagged"]) >= 1


async def test_without_current_patch_nothing_breaks(client: AsyncClient, db: AsyncSession) -> None:
    import sqlalchemy as sa

    await db.execute(sa.update(Patch).values(is_current=False))
    await db.commit()
    assert (await client.get("/overview")).json()["patch"] is None
    assert (await client.get("/connectivity")).json() == {
        "patch": None,
        "dimensions": [],
        "tier": None,
    }
    assert (await client.get("/coverage")).status_code == 200
    assert (await client.get("/quality")).status_code == 200
