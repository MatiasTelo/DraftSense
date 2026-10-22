"""Las métricas de CU-07 y los indicadores del tier 2 (`docs/24-panel-admin.md` §3.1 a §3.4).

Todo es de sólo lectura. La conectividad se calcula con las aristas del job
`check_graph_connectivity` (`app.services.connectivity.edges`), pero **sin marcar ni materializar
puentes**: mirar el panel no puede cambiar lo que el sampler sirve.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections import defaultdict
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Champion, Question, QuestionType, Respondent, Response
from app.services import aggregable, app_settings, connectivity, questions, submissions

#: El umbral de `solid` de las dimensiones (`docs/26-esquema-de-salida.md` §2.4), que es el que
#: 21 §7.2 pide a la mediana de `D_n`. Si cambia allá, cambia acá.
SOLID_N: Final = 25
#: El de `limited`, para la tercera banda de la matriz de cobertura.
LIMITED_N: Final = 10
#: Dimensiones conectadas que pide 21 §7.2 para habilitar el tier 2.
MIN_CONNECTED: Final = 6

TRUST_BINS: Final = 20
VOLUME_WINDOWS: Final = (7, 30, 90)
DEFAULT_TIMEZONE: Final = "America/Argentina/Buenos_Aires"
DECISIVE: Final = ("a", "b")


async def _timezone(session: AsyncSession) -> str:
    """El día se corta donde lo corta la racha de días (`gamification.streak_timezone`)."""
    return str(await app_settings.get(session, "gamification.streak_timezone", DEFAULT_TIMEZONE))


async def dimension_counts(session: AsyncSession, patch_id: int) -> dict[tuple[int, int], int]:
    """`D_n` por (campeón, dimensión): el `score_n` de `25-agregacion.md` §5.1.

    Respuestas agregables del tipo 1 del parche con `choice ∈ {a, b}`, contadas para cada uno de
    los dos campeones del par. Cada una de las diez filas de un ranking es una comparación.
    """
    threshold = await aggregable.min_trust(session)
    rows = await session.execute(
        sa.select(
            Question.dimension_id, Question.champion_a, Question.champion_b, sa.func.count()
        )
        .select_from(aggregable.source())
        .where(
            Question.patch_id == patch_id,
            Question.type == QuestionType.PAIRWISE_DIMENSION,
            Response.answer["choice"].astext.in_(DECISIVE),
            *aggregable.conditions(threshold),
        )
        .group_by(Question.dimension_id, Question.champion_a, Question.champion_b)
    )
    counts: dict[tuple[int, int], int] = defaultdict(int)
    for dimension_id, a, b, total in rows.tuples():
        if dimension_id is None or b is None:
            continue
        counts[(a, dimension_id)] += total
        counts[(b, dimension_id)] += total
    return counts


async def connectivity_report(session: AsyncSession) -> dict[str, Any]:
    patch = await questions.current_patch(session)
    if patch is None:
        return {"patch": None, "dimensions": [], "tier": None}

    space = await questions.load_space(session)
    by_dimension = await connectivity.edges(session, patch.patch_id)
    bridge_rows = await session.execute(
        sa.select(Question.dimension_id, sa.func.count())
        .where(
            Question.patch_id == patch.patch_id,
            Question.type == QuestionType.PAIRWISE_DIMENSION,
            Question.bridge_priority,
        )
        .group_by(Question.dimension_id)
    )
    # Comprensión y no `dict(result)`: el resultado tiene `keys()` y `dict` lo trataría como un
    # mapping, intentando indexarlo.
    pending = {dimension_id: total for dimension_id, total in bridge_rows.tuples()}

    dimensions = []
    for dimension in space.dimensions:
        groups = connectivity.components(
            space.champion_ids, by_dimension.get(dimension.dimension_id, ())
        ).groups()
        dimensions.append(
            {
                "code": dimension.code,
                "label": dimension.label_es or dimension.label_en,
                "components": len(groups),
                "largest_component": max((len(g) for g in groups), default=0),
                "pending_bridges": pending.get(dimension.dimension_id, 0),
                "connected": len(groups) <= 1,
            }
        )

    tier_one = (
        await session.execute(
            sa.select(Champion.champion_id).where(Champion.is_active, Champion.pool_tier == 1)
        )
    ).scalars().all()
    counts = await dimension_counts(session, patch.patch_id)
    cells = [
        counts.get((champion_id, d.dimension_id), 0)
        for champion_id in tier_one
        for d in space.dimensions
    ]
    median = statistics.median(cells) if cells else None
    connected = sum(1 for d in dimensions if d["connected"])
    meets_median = median is not None and median >= SOLID_N
    meets_connectivity = connected >= MIN_CONNECTED
    return {
        "patch": patch.version,
        "dimensions": dimensions,
        "tier": {
            "median_dn": median,
            "median_threshold": SOLID_N,
            "connected": connected,
            "connected_threshold": MIN_CONNECTED,
            "total_dimensions": len(dimensions),
            "meets_median": meets_median,
            "meets_connectivity": meets_connectivity,
            "ready": meets_median and meets_connectivity,
        },
    }


async def overview(session: AsyncSession, days: int = 30) -> dict[str, Any]:
    if days not in VOLUME_WINDOWS:
        raise ValueError(f"la ventana tiene que ser una de {VOLUME_WINDOWS}")
    timezone = await _timezone(session)
    # El «hoy» local lo calcula Postgres, igual que el día de cada respuesta: en Windows Python no
    # trae la base de zonas horarias y `zoneinfo` fallaría sin el paquete `tzdata`.
    today: dt.date = (
        await session.execute(sa.select(sa.func.date(sa.func.timezone(timezone, sa.func.now()))))
    ).scalar_one()
    start = today - dt.timedelta(days=days - 1)
    local_day = sa.func.date(sa.func.timezone(timezone, Response.created_at))

    volume_rows = await session.execute(
        submissions.heads(
            sa.select(local_day, Response.type, sa.func.count())
            .select_from(Response)
            .where(local_day >= start)
            .group_by(local_day, Response.type)
        )
    )
    by_day: dict[dt.date, dict[str, int]] = defaultdict(dict)
    for day, kind, total in volume_rows.tuples():
        by_day[day][QuestionType(kind).value] = total
    types = [t.value for t in QuestionType]
    dates = [start + dt.timedelta(days=offset) for offset in range(days)]
    volume = [{"date": day, "counts": {t: by_day[day].get(t, 0) for t in types}} for day in dates]

    patch = await questions.current_patch(session)
    totals: dict[str, Any] = {
        "submissions": 0,
        "rows": 0,
        "aggregable_rows": 0,
        "respondents": 0,
        "flagged_respondents": 0,
    }
    if patch is not None:
        in_patch = Response.patch_id == patch.patch_id
        totals["rows"] = (
            await session.execute(sa.select(sa.func.count()).select_from(Response).where(in_patch))
        ).scalar_one()
        totals["submissions"] = (
            await session.execute(
                submissions.heads(sa.select(sa.func.count()).select_from(Response).where(in_patch))
            )
        ).scalar_one()
        threshold = await aggregable.min_trust(session)
        totals["aggregable_rows"] = (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(aggregable.source())
                .where(Question.patch_id == patch.patch_id, *aggregable.conditions(threshold))
            )
        ).scalar_one()
        active = sa.select(Response.respondent_id).where(in_patch).distinct().subquery()
        totals["respondents"] = (
            await session.execute(sa.select(sa.func.count()).select_from(active))
        ).scalar_one()
        totals["flagged_respondents"] = (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(Respondent)
                .where(Respondent.respondent_id.in_(sa.select(active)), Respondent.is_flagged)
            )
        ).scalar_one()

    report = await connectivity_report(session)
    return {
        "patch": patch.version if patch is not None else None,
        "timezone": timezone,
        "today": today,
        "today_submissions": sum(by_day[today].values()),
        "totals": totals,
        "connected_dimensions": report["tier"]["connected"] if report["tier"] else 0,
        "total_dimensions": report["tier"]["total_dimensions"] if report["tier"] else 0,
        "days": days,
        "types": types,
        "volume": volume,
    }


async def coverage(session: AsyncSession) -> dict[str, Any]:
    """La matriz campeón por dimensión del pool habilitado, ordenada por la `D_n` mínima."""
    patch = await questions.current_patch(session)
    space = await questions.load_space(session)
    counts = await dimension_counts(session, patch.patch_id) if patch is not None else {}
    rows = []
    for champion in space.champions:
        cells = {
            d.code: counts.get((champion.champion_id, d.dimension_id), 0)
            for d in space.dimensions
        }
        rows.append(
            {
                "champion_id": champion.champion_id,
                "name": champion.display_name,
                "pool_tier": champion.pool_tier,
                "roles": [role.value for role in champion.roles],
                "counts": cells,
                "min": min(cells.values(), default=0),
            }
        )
    rows.sort(key=lambda r: (r["min"], r["name"]))
    return {
        "patch": patch.version if patch is not None else None,
        "dimensions": [
            {"code": d.code, "label": d.label_es or d.label_en} for d in space.dimensions
        ],
        "bands": {"solid": SOLID_N, "limited": LIMITED_N},
        "champions": rows,
    }


async def quality(session: AsyncSession) -> dict[str, Any]:
    """La distribución del trust —nunca el de alguien— y los respondedores marcados."""
    patch = await questions.current_patch(session)
    bins = [0] * TRUST_BINS
    if patch is not None:
        active = sa.select(Response.respondent_id).where(Response.patch_id == patch.patch_id)
        scores = (
            await session.execute(
                sa.select(Respondent.trust_score).where(Respondent.respondent_id.in_(active))
            )
        ).scalars()
        for score in scores:
            bins[min(int(float(score) * TRUST_BINS), TRUST_BINS - 1)] += 1

    flagged = (
        await session.execute(
            sa.select(Respondent)
            .where(Respondent.is_flagged)
            .order_by(Respondent.last_seen.desc())
        )
    ).scalars()
    return {
        "patch": patch.version if patch is not None else None,
        "min_trust": float(await aggregable.min_trust(session)),
        "histogram": [
            {"from": i / TRUST_BINS, "to": (i + 1) / TRUST_BINS, "count": count}
            for i, count in enumerate(bins)
        ],
        "flagged": [
            {
                "respondent_id": r.respondent_id,
                "short_id": str(r.respondent_id)[:8],
                "answers_count": r.answers_count,
                "first_seen": r.first_seen,
                "last_seen": r.last_seen,
            }
            for r in flagged
        ],
    }
