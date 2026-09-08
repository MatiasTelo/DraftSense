# Tests y base de datos

## Cómo están armados los tests

`tests/test_schema.py` trabaja en dos niveles, porque no toda máquina de desarrollo tiene Postgres:

- **Sin base de datos.** Genera el SQL de la migración en modo offline y lo compara contra los
  modelos. Corre en cualquier lado.
- **Con base de datos.** Aplica la migración de verdad y le pide a Alembic que compare el resultado
  contra los modelos. Es la prueba fuerte; **corre siempre en CI** contra un Postgres 17 real.

Los que necesitan base se saltean solos si no hay `DS_DATABASE_URL`. Con un `backend/.env`
configurado corren los diez.

## `conftest.py` y el `.env`

`tests/conftest.py` carga `backend/.env` al entorno **antes** de que los tests decidan si hay base.
Sin eso, `pytest` a secas saltearía los tests que la requieren aunque el desarrollador ya tenga su
`.env`, y sólo correrían en CI.

Usa `os.environ.setdefault`, no asignación directa: **las variables que ya vienen del entorno tienen
prioridad**, que es como CI inyecta su propio Postgres. Si cambiás eso, CI empieza a testear contra
la base de desarrollo.

## Configuración de pytest

`asyncio_mode = "auto"` — los tests `async def` no llevan decorador. `testpaths = ["tests"]`.

## Drivers

Dos, y no son intercambiables:

| Driver | Para qué | Opción de SSL |
|---|---|---|
| `asyncpg` | La aplicación y Alembic (`postgresql+asyncpg://`) | `?ssl=require` |
| `psycopg` | Las pruebas no async (`sync_url()` en `test_schema.py`) | `sslmode` |

`sync_url()` traduce el DSN de uno al otro. Si tocás el formato del DSN, tocá esa función.

## Cuando la base no conecta

Antes de debuggear el código, descartar lo de siempre con Supabase (detalle en
`sqlalchemy-alembic.md`):

1. ¿Es la cadena del **Session pooler, puerto 5432**? La conexión directa sólo publica AAAA y no
   resuelve sin IPv6; el pooler transaccional (6543) no admite sentencias preparadas y Alembic falla
   contra él.
2. ¿El DSN lleva `?ssl=require`?
3. ¿`backend/.env` existe y tiene `DS_DATABASE_URL`?

Para ver qué DSN está usando la aplicación sin filtrar la contraseña:
`Settings.masked_database_url`. **Nunca imprimas `database_url` crudo.**

## Qué corre CI

`.github/workflows/ci.yml`, job `backend`, en este orden: `pip install -e ".[dev]"` →
`ruff check .` → `mypy app` → `python -m app.cli check-seeds --seeds-dir ../infra/seeds` →
`alembic upgrade head` → `alembic downgrade base && alembic upgrade head` → `pytest -q`.

Levanta un `postgres:17` como service con `DS_DATABASE_URL` apuntando a localhost. Reproducirlo
local es correr los mismos comandos con un `.env` configurado.
