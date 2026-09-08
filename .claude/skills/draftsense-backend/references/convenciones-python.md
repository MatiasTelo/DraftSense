# Convenciones de Python

## Herramientas y su configuración

| Herramienta | Dónde se configura | Qué fija |
|---|---|---|
| ruff | `backend/pyproject.toml` `[tool.ruff]` | `line-length = 100`, `target-version = "py312"`, reglas `E, F, I, N, UP, B, SIM, RUF` |
| ruff (fuera de backend) | `ruff.toml` en la raíz del repo | **Las mismas reglas**, para `infra/` |
| mypy | `backend/pyproject.toml` `[tool.mypy]` | `python_version = "3.12"`, `strict = true`, excluye `migrations/versions/` |
| pytest | `backend/pyproject.toml` `[tool.pytest.ini_options]` | `asyncio_mode = "auto"`, `testpaths = ["tests"]` |

> **Las dos configuraciones de ruff se mueven juntas.** El `ruff.toml` de la raíz existe justamente
> porque sin él ruff aplicaría sus defaults a `infra/`, y el lint pasaría en una máquina y fallaría
> en otra según desde dónde se lo invoque. Si cambiás una regla, cambiala en las dos.

`mypy` corre sólo sobre `app` (`mypy app`). `migrations/versions/` está excluido porque Alembic
genera módulos sin anotaciones que no aportan nada al chequeo.

## Estilo

- **`from __future__ import annotations` en todos los módulos**, primera línea después del docstring.
- **Todo anotado.** `strict = true` no perdona: parámetros, retornos y atributos. Usar sintaxis
  moderna (`X | None`, no `Optional[X]`; `list[str]`, no `List[str]`) — la regla `UP` lo exige.
- **Docstring de módulo siempre**, en español, diciendo qué resuelve el módulo. Una línea alcanza
  si el módulo es obvio (`"""Motor y sesiones asincrónicas."""`).
- **Los comentarios explican por qué, no qué.** El estándar del repo es alto: mirá
  `app/models/base.py`, que no dice "convención de nombres" sino *"sin esto, Alembic genera nombres
  distintos en cada corrida y los `downgrade()` no encuentran qué borrar"*. Si un comentario no dice
  qué se rompe al cambiar la línea, probablemente sobre.
- **Comentarios de atributo con `#:`** para documentar constantes y campos, como en `config.py`.
- **Referencias cruzadas a la documentación en los docstrings**: `Ver docs/20-tipos-de-pregunta.md §4`.
  Es lo que mantiene el código atado a la especificación.

## Patrones ya establecidos en el repo

Seguirlos en vez de inventar otros:

- **Configuración:** `Settings(BaseSettings)` con `env_prefix="DS_"` y `env_file=".env"`, expuesta
  por `get_settings()` cacheada con `@lru_cache` (`app/config.py`). Nunca leer `os.environ` suelto
  en el código de aplicación.
- **Secretos en logs:** `Settings.masked_database_url` existe para eso. **Nunca loguear
  `database_url` crudo.**
- **Motor y sesiones:** singletons perezosos en `app/db.py` (`get_engine`, `get_sessionmaker`), y
  `get_session()` como dependencia asincrónica de FastAPI, una sesión por request.
  `expire_on_commit=False`, `pool_pre_ping=True`.
- **Enums:** `StrEnum` en `app/models/enums.py`, con los valores **exactamente** iguales a los del
  DDL de `docs/11-modelo-de-datos.md`, para que el valor que viaja a Postgres y el que serializa
  Pydantic sean el mismo. `ALL_ENUMS` los agrupa para los tests.
- **Paquetes:** `app*` es lo único que empaqueta setuptools. El CLI se expone como
  `draftsense = "app.cli:main"`.

## Antes de cerrar cualquier cambio

```bash
cd backend && ruff check . && mypy app && pytest -q
```

Si tocaste `infra/`, además: `ruff check infra` desde la raíz del repo (es lo que corre el job
`docs` de CI, junto con `python infra/check_docs.py`).
