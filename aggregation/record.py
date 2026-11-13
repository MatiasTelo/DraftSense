"""El paso 8 de `docs/25-agregacion.md` §8.2: una fila en `exports` por archivo (CA-407).

Con los parámetros efectivamente usados —en sus columnas y, todos juntos, en `params`— y con
`responses` append-only, cualquier corrida vieja se reproduce leyendo esta fila y volviendo a pasar
sus valores por la línea de comandos (CA-408).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from aggregation import AGGREGATION_VERSION
from aggregation.load import Dataset
from aggregation.params import RunParams
from aggregation.writers import Written
from app.models import Export


async def insert(
    session: AsyncSession,
    data: Dataset,
    params: RunParams,
    written: Sequence[Written],
    included: Mapping[str, tuple[int, int]],
    folder: str,
) -> list[int]:
    """`folder` es el nombre de la carpeta donde quedaron los archivos.

    Va en `params` y no sale de `as_record()` a propósito: no es un parámetro de la corrida —no
    cambia ni un byte de los archivos ni entra en el informe—, es dónde buscarlos después. El
    panel lo usa para la descarga (24 §3.9).
    """
    stored = {
        **params.as_record(),
        "folder": folder,
        # El pool no es un parámetro de la línea de comandos —sale de `champions` y de
        # `sampler.enabled_pool_tiers` al correr—, pero decide qué filas tiene cada archivo:
        # sin registrarlo no se puede saber si una corrida vieja usó el mismo (25 §8.3).
        "pool_champion_ids": list(data.pool),
    }
    rows = []
    for file in written:
        responses, respondents = included[file.kind]
        rows.append(
            Export(
                patch_id=data.patch_id,
                file_name=file.file_name,
                file_kind=file.kind,
                sha256=file.sha256,
                row_count=file.rows,
                column_count=file.columns,
                responses_included=responses,
                respondents_included=respondents,
                min_trust_applied=params.min_trust,
                patch_window=params.patch_window,
                decay_halflife_days=Decimal(str(params.halflife)),
                bootstrap_samples=params.bootstrap,
                aggregation_version=AGGREGATION_VERSION,
                params=stored,
            )
        )
    session.add_all(rows)
    await session.commit()
    return [row.export_id for row in rows]
