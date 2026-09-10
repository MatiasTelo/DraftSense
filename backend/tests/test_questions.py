"""Entrega de preguntas — CA-101, CA-103 y CA-104 de `docs/03-criterios-aceptacion.md` §2.

Sólo cubren el tipo 1: los otros cuatro son de las semanas 4 y 8, y el sampler completo de la 5.
"""

from __future__ import annotations

import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Champion, Dimension, Patch, Question, Respondent
from tests.conftest import as_respondent, requires_db


@requires_db
async def test_entrega_por_lotes(
    client: AsyncClient,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """CA-101 — se piden 5, llegan 5, y ninguna repetida dentro del lote."""
    _, token = respondent
    response = await as_respondent(client, token).get("/questions/next?count=5")

    assert response.status_code == 200
    questions = response.json()["questions"]
    assert len(questions) == 5

    ids = [q["question_id"] for q in questions]
    assert len(set(ids)) == len(ids)


@requires_db
async def test_los_honeypots_son_indistinguibles(
    client: AsyncClient,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """CA-103 — `is_honeypot` y `expected_answer` no aparecen en ninguna forma.

    Se inspecciona el cuerpo crudo y no el objeto parseado: un campo de más se colaría igual si
    sólo se miraran las claves que el schema declara.
    """
    _, token = respondent
    response = await as_respondent(client, token).get("/questions/next?count=3")

    raw = response.text
    assert "is_honeypot" not in raw
    assert "expected_answer" not in raw
    assert "exposure_count" not in raw
    assert "entropy" not in raw


@requires_db
async def test_el_enunciado_llega_compuesto(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """CA-104 — el texto sale de `dimensions`, no de una plantilla sin resolver.

    Se compara contra la dimensión **de la pregunta que llegó**, no contra la del fixture: el
    sampler sortea entre todas las dimensiones activas, y con el catálogo sembrado el fixture es
    una de nueve. Amarrar el test a una en particular lo haría fallar según qué sorteo salga.
    """
    _, token = respondent
    response = await as_respondent(client, token).get("/questions/next?count=1")

    payload = response.json()["questions"][0]
    assert payload["type"] == "pairwise_dimension"

    source = (
        await db.execute(
            sa.select(Dimension)
            .join(Question, Question.dimension_id == Dimension.dimension_id)
            .where(Question.question_id == payload["question_id"])
        )
    ).scalar_one()

    assert payload["prompt"] == source.prompt_en
    assert payload["help"] == {"label": source.label_en, "text": source.description_en}
    assert "{" not in payload["prompt"]


@requires_db
async def test_toda_opcion_comparable_lleva_arreglo(
    client: AsyncClient,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """`docs/12-api.md` §1.2 — el cliente renderiza duplas y campeones con el mismo componente."""
    _, token = respondent
    response = await as_respondent(client, token).get("/questions/next?count=1")

    options = response.json()["questions"][0]["options"]
    assert [o["key"] for o in options] == ["a", "b", "unknown"]
    assert all(isinstance(o["champions"], list) for o in options)
    assert len(options[0]["champions"]) == 1
    assert options[2]["champions"] == []
    assert options[2]["label"] == "Not sure"

    champion = options[0]["champions"][0]
    assert set(champion) == {"id", "key", "name", "image_url"}


@requires_db
async def test_count_fuera_de_rango(
    client: AsyncClient, respondent: tuple[Respondent, str]
) -> None:
    """`docs/12-api.md` §3 — `invalid_parameter`, con el campo señalado."""
    _, token = respondent
    response = await as_respondent(client, token).get("/questions/next?count=99")

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_parameter"
    assert error["field"] == "count"


@requires_db
async def test_sin_pool_habilitado_devuelve_lote_vacio(
    client: AsyncClient,
    db: AsyncSession,
    respondent: tuple[Respondent, str],
    patch: Patch,
    champions: list[Champion],
    dimension: Dimension,
) -> None:
    """Sin campeones de tier habilitado no hay de dónde sacar preguntas, y eso no es un error.

    El tier se baja explícitamente en vez de confiar en que la base esté vacía: el snapshot de
    pick rate deja 58 campeones en tier 1, y el test tiene que valer igual después de sembrarlo.
    """
    await db.execute(sa.update(Champion).values(pool_tier=3))
    await db.commit()

    _, token = respondent
    response = await as_respondent(client, token).get("/questions/next?count=5")

    assert response.status_code == 200
    assert response.json()["questions"] == []
