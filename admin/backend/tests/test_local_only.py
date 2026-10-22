"""El panel sólo atiende desde la máquina (CA-605, ADR-025) y sus piezas sin base."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.models import QuestionType
from draftsense_admin.config import HOST
from draftsense_admin.main import create_app, is_loopback
from draftsense_admin.services import audit, seeds


def test_host_is_loopback() -> None:
    """Si alguien cambia la constante, el panel queda abierto a la red sin clave."""
    assert HOST == "127.0.0.1"


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("10.0.0.5", False),
        ("192.168.1.20", False),
        (None, False),
    ],
)
def test_is_loopback(host: str | None, expected: bool) -> None:
    assert is_loopback(host) is expected


async def test_other_machines_get_403(tmp_path: Path) -> None:
    transport = ASGITransport(app=create_app(static_dir=tmp_path), client=("10.0.0.5", 4321))
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get("/api/overview")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "local_only"


async def test_spa_fallback_serves_index(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>admin</title>", encoding="utf-8")
    (tmp_path / "app.js").write_text("console.log(1)", encoding="utf-8")
    transport = ASGITransport(app=create_app(static_dir=tmp_path))
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        route = await http.get("/conectividad")
        asset = await http.get("/app.js")
        missing_api = await http.get("/api/no-existe")
    assert route.status_code == 200 and "admin" in route.text
    assert asset.text == "console.log(1)"
    assert missing_api.status_code == 404


async def test_spa_without_build_says_so(tmp_path: Path) -> None:
    transport = ASGITransport(app=create_app(static_dir=tmp_path))
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get("/")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "frontend_not_built"


# ------------------------------------------------------------------------------- seeds (CA-611)


def _seeds_dir(tmp_path: Path) -> Path:
    (tmp_path / "pick_rate_99.99.csv").write_text("role,champion_name\n", encoding="utf-8")
    (tmp_path / "honeypots_99.99.yaml").write_text("[]\n", encoding="utf-8")
    (tmp_path / "otra_cosa.txt").write_text("no", encoding="utf-8")
    return tmp_path


def test_seed_files_are_listed_by_kind(tmp_path: Path) -> None:
    files = seeds.list_files(_seeds_dir(tmp_path))
    assert files["pick_rate"] == ["pick_rate_99.99.csv"]
    assert files["honeypots"] == ["honeypots_99.99.yaml"]
    assert files["ddragon_snapshot"] == []


@pytest.mark.parametrize(
    "name",
    ["../backend/.env", "..\\backend\\.env", "otra_cosa.txt", "honeypots_99.99.yaml", ""],
)
def test_seed_file_outside_the_list_is_rejected(tmp_path: Path, name: str) -> None:
    with pytest.raises(seeds.SeedFileNotAllowedError):
        seeds.resolve(_seeds_dir(tmp_path), "pick_rate", name)


def test_seed_file_in_the_list_resolves(tmp_path: Path) -> None:
    directory = _seeds_dir(tmp_path)
    assert seeds.resolve(directory, "pick_rate", "pick_rate_99.99.csv") == (
        directory / "pick_rate_99.99.csv"
    )


# ------------------------------------------------------------------------------------- audit


def test_plain_makes_payloads_json_safe() -> None:
    respondent = uuid.uuid4()
    value = audit.plain(
        {
            "when": dt.date(2026, 10, 21),
            "trust": Decimal("0.300"),
            "type": QuestionType.PEAK_TIMING,
            "who": respondent,
            "ids": {3, 1},
        }
    )
    assert value == {
        "when": "2026-10-21",
        "trust": 0.3,
        "type": "peak_timing",
        "who": str(respondent),
        "ids": [1, 3],
    }


def test_unknown_audit_action_is_rejected() -> None:
    with pytest.raises(ValueError, match="desconocida"):
        audit.record(None, "delete_everything", {})  # type: ignore[arg-type]
