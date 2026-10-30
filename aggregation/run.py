"""`python -m aggregation.run` — la interfaz de `docs/25-agregacion.md` §8.1.

```
python -m aggregation.run --patch-window 16.18..16.20 --min-trust 0.30 --halflife 21 \\
    --sigma 7.5 --bootstrap 2000 --exported-at 2026-11-10 --out exports/
```

Todo parámetro omitido sale de `app_settings` (§9), y `--exported-at`, de la fecha de hoy: para
reproducir una corrida vieja hay que pasar la fecha registrada en `exports.params` (CA-408).

La base es la de `DS_DATABASE_URL`, como el resto del sistema. **Corre contra la base que diga el
entorno**: para probar, apuntalo al Postgres de Docker, nunca a staging.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys
from pathlib import Path

from aggregation import params as run_params
from aggregation import pipeline
from aggregation.load import NoDataError
from app.config import get_settings
from app.db import get_sessionmaker
from app.services import questions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m aggregation.run",
        description="Corre el pipeline de agregación y escribe los seis CSV (docs/25 §8).",
    )
    parser.add_argument("--patch-window", help="16.18..16.20; por defecto, el parche vigente")
    parser.add_argument("--min-trust", type=float, help="por defecto, export.min_trust")
    parser.add_argument("--halflife", type=float, help="días; aggregation.decay_halflife_days")
    parser.add_argument("--sigma", type=float, help="ancho de la curva; aggregation.power_sigma")
    parser.add_argument("--bootstrap", type=int, help="aggregation.bootstrap_samples")
    parser.add_argument("--exported-at", type=dt.date.fromisoformat, help="AAAA-MM-DD; hoy")
    parser.add_argument("--out", type=Path, default=Path("exports"), help="carpeta de salida")
    parser.add_argument(
        "--workers", type=int, help="procesos para los 15 ajustes; 1 los corre en serie"
    )
    return parser


async def main_async(args: argparse.Namespace) -> int:
    print(f"base: {get_settings().masked_database_url}")
    async with get_sessionmaker()() as session:
        patch = await questions.current_patch(session)
        try:
            resolved = await run_params.resolve(
                session,
                patch_window=args.patch_window,
                current_patch=patch.version if patch is not None else None,
                min_trust=args.min_trust,
                halflife=args.halflife,
                sigma=args.sigma,
                bootstrap=args.bootstrap,
                exported_at=args.exported_at,
            )
            result = await pipeline.run(session, resolved, args.out, workers=args.workers)
        except (NoDataError, ValueError) as exc:
            print(f"ERROR {exc}", file=sys.stderr)
            return 1

    print(
        f"OK  {resolved.patch_window} · {result.responses} respuestas de "
        f"{result.respondents} respondedores · semilla {resolved.seed}"
    )
    for file in result.files:
        print(f"    {file.file_name}  {file.rows} filas  {file.sha256}")
    for report in result.reports:
        if report.failed:
            print(
                f"AVISO {report.name}: {report.discarded} de {report.attempts} remuestreos "
                "descartados; la magnitud sale insufficient"
            )
        elif report.components > 1:
            print(f"AVISO {report.name}: {report.components} componentes (ADR-008)")
    return 0


def main() -> None:
    sys.exit(asyncio.run(main_async(build_parser().parse_args())))


if __name__ == "__main__":
    main()
