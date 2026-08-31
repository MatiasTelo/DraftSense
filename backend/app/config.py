"""Configuración leída del entorno."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DS_", extra="ignore")

    #: DSN asincrónico usado por la aplicación: postgresql+asyncpg://...
    database_url: str = Field(
        default="postgresql+asyncpg://draftsense:draftsense@localhost:5432/draftsense"
    )
    #: Clave de los endpoints /admin/*.
    admin_key: str = Field(default="")
    #: Origen permitido por CORS. Con credenciales no puede ser comodín.
    cors_origin: str = Field(default="http://localhost:5173")
    #: URL base de Data Dragon, para el seeder de campeones.
    ddragon_base_url: str = Field(default="https://ddragon.leagueoflegends.com")

    @property
    def masked_database_url(self) -> str:
        """El DSN con la contraseña oculta, apto para logs."""
        url = self.database_url
        if "@" not in url or "//" not in url:
            return url
        scheme, rest = url.split("//", 1)
        credentials, host = rest.split("@", 1)
        user = credentials.split(":", 1)[0]
        return f"{scheme}//{user}:***@{host}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
