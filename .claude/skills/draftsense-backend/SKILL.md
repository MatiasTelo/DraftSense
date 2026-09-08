---
name: draftsense-backend
description: >-
  Backend de DraftSense: FastAPI 0.115 + SQLAlchemy 2.0 asincrónico + asyncpg + Alembic + Pydantic v2
  + pytest-asyncio sobre Python 3.12, con ruff y mypy strict. Usar SIEMPRE al escribir, revisar o
  refactorizar cualquier cosa bajo `backend/` o `infra/`: endpoints, routers, modelos ORM,
  migraciones, seeds, comandos de CLI, tests, o configuración de ruff/mypy/pytest. Activar también
  ante SQLAlchemy declarativo, `async_sessionmaker`, dependencias de FastAPI, Alembic
  upgrade/downgrade, enums nativos de Postgres, jsonb, índices parciales, `NULLS NOT DISTINCT`,
  Pydantic Settings, o problemas para conectarse a la base (Supabase, asyncpg, psycopg, SSL,
  DS_DATABASE_URL). Complementa a `draftsense` (que fija el alcance y rutea a la documentación):
  el contrato de cada endpoint se lee de `docs/12-api.md` y el esquema de `docs/11-modelo-de-datos.md`;
  esta skill dice CÓMO escribir el código que los implementa.
---

# Backend de DraftSense

Python 3.12, FastAPI, SQLAlchemy 2.0 async sobre `asyncpg`, Pydantic v2, Alembic, PostgreSQL 15+.
Decidido en [ADR-007](../../../docs/13-adr/ADR-007-fastapi-python.md).

## Estado actual

`backend/app/` tiene `config.py`, `db.py`, `cli.py`, `models/` y `seeds/`. **Todavía no hay
endpoints**: no existe `main.py` ni routers. Eso es el trabajo de la semana 2. Hay 10 tests de
esquema en `tests/test_schema.py`.

## Comandos

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate   # source .venv/bin/activate en Linux/macOS
pip install -e ".[dev]"

ruff check . && mypy app && pytest -q             # las tres comprobaciones, en ese orden

alembic upgrade head                              # crea el esquema
alembic downgrade base && alembic upgrade head    # lo que corre CI: la migración debe ser reversible

python -m app.cli check-seeds                     # valida los YAML sin tocar la base
python -m app.cli seed-catalog                    # 8 dimensiones y 7 atributos
python -m app.cli seed-champions --patch 16.20    # relee Data Dragon
python -m app.cli fetch-ddragon --out ../infra/seeds/ddragon_champions_snapshot.json
```

La configuración se lee del entorno con prefijo `DS_` y desde `backend/.env`
(`DS_DATABASE_URL`, `DS_ADMIN_KEY`, `DS_CORS_ORIGIN`, `DS_DDRAGON_BASE_URL`). **`.env` está en
`.gitignore` y nunca se versiona.**

## Las cinco reglas que no se negocian

1. **`responses` es append-only.** Nunca un `UPDATE` ni un `DELETE` sobre esa tabla. Las
   correcciones de calidad son pesos en la agregación y filtros en el export. Lo garantizan los
   permisos de Postgres, no la disciplina del código ([ADR-002](../../../docs/13-adr/ADR-002-responses-append-only.md)).
2. **El trust score nunca sale de la API** (RF-207). Ni en `/me`, ni en el leaderboard, ni en un
   mensaje de error. Es de uso interno.
3. **Toda migración tiene que ser reversible.** CI corre `downgrade base` y vuelve a subir. Un
   `downgrade()` incompleto rompe el build.
4. **El servidor arma los textos, el cliente los muestra** (`docs/12-api.md` §1.1). El enunciado
   viaja compuesto, con los nombres de campeón ya sustituidos.
5. **Sin autenticación de usuario.** Sesión anónima por cookie `ds_session`; en base sólo el
   SHA-256 del token ([ADR-001](../../../docs/13-adr/ADR-001-sin-autenticacion.md)). Los endpoints
   `/admin/*` sí van con `DS_ADMIN_KEY`.

## Cuándo leer cada referencia

- **`references/convenciones-python.md`** — al escribir cualquier `.py`. Estilo, tipado, ruff, mypy.
- **`references/sqlalchemy-alembic.md`** — al tocar modelos, migraciones o el esquema.
- **`references/fastapi-contrato.md`** — al escribir un endpoint, un schema de Pydantic o manejo de
  errores.
- **`references/tests-y-base.md`** — al escribir tests, o cuando la base no conecta.

## Mantener esta skill al día

Si cambian `docs/12-api.md`, `docs/11-modelo-de-datos.md`, `backend/pyproject.toml`, `ruff.toml` o
`.github/workflows/ci.yml`, revisar que las referencias de acá sigan siendo ciertas. Esta skill no
copia el contrato de la API ni el DDL: los rutea.
