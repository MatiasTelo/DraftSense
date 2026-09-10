"""Lo transversal del contrato: la sonda de salud y la forma de los errores.

El test del sobre de error es la contrapartida de ADR-015: devolver un `HTTPException` de FastAPI
a mano produce `{"detail": ...}` y rompe el contrato **en silencio**, porque el cliente no valida
la forma del error y simplemente no encuentra `error.code`. Este test recorre los errores que la
semana 2 puede producir y verifica que todos tengan la misma forma.
"""

from __future__ import annotations

from httpx import AsyncClient

from app.models import Patch, Respondent
from tests.conftest import as_respondent, requires_db


@requires_db
async def test_health(client: AsyncClient, patch: Patch) -> None:
    """`docs/12-api.md` §2.7 — conectividad a la base y parche vigente. Sin autenticación."""
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "current_patch": patch.version, "db": "ok"}


@requires_db
async def test_todos_los_errores_usan_el_mismo_sobre(
    client: AsyncClient, respondent: tuple[Respondent, str]
) -> None:
    """Ningún error puede salir con la forma de FastAPI en vez de la del contrato."""
    _, token = respondent
    http = as_respondent(client, token)

    casos = [
        # (respuesta, código esperado)
        (await http.get("/questions/next?count=99"), "invalid_parameter"),
        (await http.get("/leaderboard?window=month"), "invalid_parameter"),
        (
            await http.post(
                "/responses",
                json={
                    "question_id": 999_999_999,
                    "answer": {"choice": "a"},
                    "response_time_ms": 1,
                },
            ),
            "question_not_found",
        ),
        (
            await http.post("/sessions/onboarding", json={"declared_rank": "radiant"}),
            "invalid_parameter",
        ),
        # 422 de Pydantic: `response_time_ms` fuera del rango del contrato.
        (
            await http.post(
                "/responses",
                json={"question_id": 1, "answer": {}, "response_time_ms": -5},
            ),
            "validation_error",
        ),
    ]

    for response, expected in casos:
        body = response.json()
        assert "detail" not in body, f"{response.url} devolvió el sobre de FastAPI"
        assert set(body) == {"error"}, f"{response.url}: {body}"
        assert body["error"]["code"] == expected, f"{response.url}: {body}"
        assert isinstance(body["error"]["message"], str)


@requires_db
async def test_la_openapi_expone_los_siete_endpoints(client: AsyncClient) -> None:
    """El contrato publicado tiene que ser el de `docs/12-api.md` §2, sin los `/admin/*`."""
    from app.main import app

    paths = set(app.openapi()["paths"])

    assert paths == {
        "/api/v1/health",
        "/api/v1/sessions",
        "/api/v1/sessions/onboarding",
        "/api/v1/questions/next",
        "/api/v1/responses",
        "/api/v1/me",
        "/api/v1/leaderboard",
    }
    assert not any("admin" in path for path in paths)
