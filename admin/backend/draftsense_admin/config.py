"""Configuración de la app admin, leída de `admin/.env` y del entorno.

Hereda de la `Settings` del backend para compartir los nombres de las variables (`DS_DATABASE_URL`,
`DS_DDRAGON_BASE_URL`) y `masked_database_url`, pero lee **su propio** archivo: el admin corre en
el servidor del laboratorio con sus credenciales, no con las de `backend/.env` (ADR-025 §5).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Final

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from app.config import Settings

#: `admin/`, la carpeta que tiene `.env`, `backend/` y `frontend/`.
ADMIN_ROOT: Final = Path(__file__).resolve().parents[2]
REPO_ROOT: Final = ADMIN_ROOT.parent

#: El host **no es configurable**. Que la app sólo atienda desde la máquina del servidor es lo que
#: reemplaza a la clave (ADR-025 §1): si se pudiera cambiar por una variable, un `.env` copiado de
#: otro lado la abriría a toda la red del laboratorio sin que nadie lo note.
HOST: Final = "127.0.0.1"


class AdminSettings(Settings):
    model_config = SettingsConfigDict(
        env_file=ADMIN_ROOT / ".env", env_prefix="DS_", extra="ignore"
    )

    #: Puerto de la app admin (`docs/24-panel-admin.md` §1).
    admin_port: int = Field(default=5000)
    #: De dónde salen los archivos de los seeds. El panel no sube archivos: elige entre éstos.
    seeds_dir: Path = Field(default=REPO_ROOT / "infra" / "seeds")
    #: El build del frontend admin, que este proceso sirve como estáticos.
    static_dir: Path = Field(default=ADMIN_ROOT / "frontend" / "dist")


@lru_cache
def get_admin_settings() -> AdminSettings:
    return AdminSettings()
