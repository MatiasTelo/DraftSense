"""La seed sintética (`services/synthetic.py`): la guarda de base local y que la verdad sea
determinista. Una corrida chica de punta a punta, dentro de la transacción del test."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LaneRole, Patch, Respondent, Response, Trait
from app.services import synthetic
from tests.conftest import make_champions, make_dimensions, requires_db, restrict_pool

SMALL = synthetic.SeedPlan(
    respondents=12,
    groups_per_dimension=1,
    group_answers=3,
    random_rankings_per_dimension=4,
    peak_answers=3,
    trait_answers=3,
    lane_answers=2,
    duo_questions_per_context=2,
    duo_answers=2,
    honeypot_every=5,
    retests_per_respondent=1,
)


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("postgresql+asyncpg://u:p@127.0.0.1:5433/draftsense", True),
        ("postgresql+asyncpg://u:p@localhost/draftsense", True),
        ("postgresql+asyncpg://u:p@staging.example.org:6543/postgres", False),
        ("postgresql+asyncpg://u:p@10.0.0.5/draftsense", False),
    ],
)
def test_la_seed_solo_corre_contra_una_base_local(
    monkeypatch: pytest.MonkeyPatch, url: str, allowed: bool
) -> None:
    monkeypatch.setattr(synthetic, "get_settings", lambda: SimpleNamespace(database_url=url))
    if allowed:
        assert synthetic.guard()
    else:
        with pytest.raises(synthetic.UnsafeDatabaseError):
            synthetic.guard()


def test_el_nivel_ordinal_respeta_el_signo() -> None:
    import random

    rng = random.Random(1)
    cuts = [-1.8, -0.6, 0.6, 1.8]
    strong = [synthetic.ordinal_level(4.0, cuts, rng) for _ in range(500)]
    weak = [synthetic.ordinal_level(-4.0, cuts, rng) for _ in range(500)]
    assert sum(strong) / 500 > 3.5
    assert sum(weak) / 500 < 0.5


async def _world(db: AsyncSession, patch: Patch) -> None:
    champions = await make_champions(db, patch, 6, roles=[LaneRole.MID], prefix="SyM")
    champions += await make_champions(db, patch, 3, roles=[LaneRole.ADC], prefix="SyA")
    champions += await make_champions(db, patch, 3, roles=[LaneRole.SUPPORT], prefix="SyS")
    dimensions = await make_dimensions(db, ["sydim"])
    await restrict_pool(db, champions, dimensions)
    await db.execute(sa.update(Trait).values(is_active=False))
    db.add(Trait(code="syalpha", label_en="Alpha", description_en="Alpha.", display_order=1))
    await db.commit()


@requires_db
async def test_una_seed_chica_corre_de_punta_a_punta(
    db: AsyncSession, patch: Patch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(synthetic, "guard", lambda: "127.0.0.1")
    await _world(db, patch)

    result = await synthetic.seed(db, 7, tmp_path / "verdad.json", SMALL)

    assert result.respondents == 12
    assert result.responses > 0
    stored = (
        await db.execute(
            sa.select(sa.func.count())
            .select_from(Response)
            .join(Respondent, Respondent.respondent_id == Response.respondent_id)
            .where(Respondent.fingerprint_hash.like("synthetic-7-%"))
        )
    ).scalar_one()
    assert stored == result.responses
    truth = json.loads((tmp_path / "verdad.json").read_text(encoding="utf-8"))
    assert set(truth["dimensions"]) == {"sydim"}
    assert truth["profiles"] == result.profiles


@requires_db
async def test_la_verdad_depende_solo_de_la_semilla(
    db: AsyncSession, patch: Patch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(synthetic, "guard", lambda: "127.0.0.1")
    await _world(db, patch)

    await synthetic.seed(db, 11, tmp_path / "uno.json", SMALL)
    await synthetic.seed(db, 11, tmp_path / "dos.json", SMALL)

    first = json.loads((tmp_path / "uno.json").read_text(encoding="utf-8"))
    second = json.loads((tmp_path / "dos.json").read_text(encoding="utf-8"))
    assert first["dimensions"] == second["dimensions"]
    assert first["peak"] == second["peak"]
