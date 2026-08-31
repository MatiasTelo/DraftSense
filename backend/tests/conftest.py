"""Configuración compartida de los tests.

Carga `backend/.env` al entorno antes de que los tests decidan si hay base de datos.
Sin esto, `pytest` a secas saltearía los tests que la requieren aunque el desarrollador
ya tenga su `.env` configurado, y sólo correrían en CI. Las variables que ya vienen del
entorno tienen prioridad, que es como CI inyecta su propio Postgres.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

if _ENV_FILE.exists():
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())
