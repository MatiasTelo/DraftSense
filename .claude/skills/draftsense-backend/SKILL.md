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

Los **siete endpoints públicos** están implementados (semana 2), en cuatro capas:

| Carpeta | Qué hay |
|---|---|
| `app/routers/` | `health`, `sessions`, `questions`, `responses`, `profile` — montados en `/api/v1` |
| `app/services/` | `sessions`, `questions`, `question_texts`, `answers`, `responses`, `question_stats`, `streaks`, `profile`, `leaderboard`, `app_settings`, `alias` |
| `app/schemas/` | Los modelos Pydantic, con los campos listados uno por uno; `common.is_absent` para omitir claves |
| `app/` | `main.py`, `errors.py`, `dependencies.py`, además de `config.py`, `db.py`, `cli.py`, `models/` y `seeds/` |

La organización y sus razones están en
[ADR-015](../../../docs/13-adr/ADR-015-estructura-en-capas-del-backend.md). **Un service no importa
nada de `fastapi`**: es la regla que hace verificable todo lo demás.

Desde la semana 3 existe además el **primero de los cuatro jobs de fondo**,
`refresh_question_stats`, en `app/services/question_stats.py`: recalcula `answer_counts`,
`exposure_count` y `entropy` de las preguntas del parche vigente, que es lo que hace que
`build_feedback` deje de devolver `None` y el consenso post-respuesta se muestre. **No calcula
`coverage_deficit` ni retira honeypots**: las dos cosas dependen de módulos de la semana 5.

**Semana 4: los tipos 2 (`peak_timing`) y 3 variante 1v1 (`lane_matchup`)**, de punta a punta:

- `GET /questions/next` sirve los tres tipos: las 3 primeras de un respondedor son de tipo 1 y
  después el tipo se sortea con `TYPE_WEIGHTS` (50/20/15 renormalizado), uniforme adentro. Es
  todavía el reemplazo provisorio del sampler; lee su docstring antes de tocarlo.
- La respuesta es una unión discriminada (`QuestionOut`). Los textos de los tipos 2 y 3 son
  constantes de `question_texts.py`, no filas de la base ([ADR-018](../../../docs/13-adr/ADR-018-textos-fijos-de-los-tipos-2-y-3.md)).
- `build_feedback` devuelve la mediana entera en el tipo 2; el acuerdo del tipo 3 es contra el
  nivel exacto. Las claves que no aplican se **omiten** con `Field(exclude_if=is_absent)`, que
  exige `pydantic>=2.13`.
- El job cubre los tres tipos, cada uno con su entropía (`docs/21-sampler.md` §3.2).
- `champions.roles` sale del snapshot de pick rate
  ([ADR-019](../../../docs/13-adr/ADR-019-roles-derivados-del-snapshot.md)): lo aplica
  `seed-pick-rate`, y `sync-roles` sobre un snapshot ya cargado.

**Lo que todavía no existe, y en qué semana llega:** el sampler completo con la regla de variedad
(5), honeypots, retests y trust score (5), los `/admin/*` (7), los otros tres jobs de fondo y la
programación del worker cada 15 minutos (7 — hoy `refresh_question_stats` se dispara a mano por
CLI), la variante 2v2 del tipo 3 y los tipos 4 y 5 (8). `POST /responses` **nunca escribe
`is_retest_of`** todavía, así que CA-205 está sin cubrir.

115 tests en `tests/`: `test_schema`, `test_sessions`, `test_questions`, `test_responses`,
`test_question_stats`, `test_profile`, `test_leaderboard`, `test_seeds` y `test_api_contract`.
Los que prueban el sorteo lo hacen con `random.Random(seed)` o forzando `TYPE_WEIGHTS`, y tienen
que pasar igual contra la base vacía de CI y contra el pool real de staging.

## Comandos

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate   # source .venv/bin/activate en Linux/macOS
pip install -e ".[dev]"

ruff check . && mypy app && pytest -q             # las tres comprobaciones, en ese orden

alembic upgrade head                              # crea el esquema
alembic downgrade base && alembic upgrade head    # lo que corre CI: la migración debe ser reversible

python -m app.cli check-seeds                     # valida los seeds sin tocar la base
python -m app.cli seed-catalog                    # 8 dimensiones y 7 atributos
python -m app.cli seed-settings                   # los 33 parámetros operativos
python -m app.cli seed-champions --patch 16.17 --released-at 2026-08-25
python -m app.cli seed-pick-rate --patch 16.17 --file ../infra/seeds/pick_rate_16.17.csv     --source lolalytics --source-url URL --captured-at 2026-09-09
python -m app.cli sync-roles --patch 16.17        # roles desde el snapshot ya cargado (ADR-019)
python -m app.cli fetch-ddragon --out ../infra/seeds/ddragon_champions_snapshot.json

python -m app.cli refresh-question-stats          # recalcula answer_counts, exposure y entropía

uvicorn app.main:app --reload                     # la API en :8000, OpenAPI en /docs
```

`seed-settings` **no pisa** los valores existentes sin `--force`: `app_settings` es el estado
actual del sistema y el seed es sólo el inicial. `seed-pick-rate` deriva `pool_tier` del snapshot
con la regla de [ADR-016](../../../docs/13-adr/ADR-016-carga-inicial-del-pool.md) y los roles con
la de ADR-019. No se puede repetir sobre el mismo snapshot (restricción única por fuente, parche y
fecha): para re-aplicar los roles está `sync-roles`, que **escribe en la base** y no crea ni cambia
el parche vigente.

La configuración se lee del entorno con prefijo `DS_` y desde `backend/.env`
(`DS_DATABASE_URL`, `DS_ADMIN_KEY`, `DS_CORS_ORIGIN`, `DS_DDRAGON_BASE_URL`). **`.env` está en
`.gitignore` y nunca se versiona**; `backend/.env.example` tiene las claves sin valores.

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
   `/admin/*` sí van con `DS_ADMIN_KEY`. **No tener sesión no es un error:** los endpoints que
   necesitan identidad la crean al vuelo y devuelven la cookie (`docs/12-api.md` §1.3).
6. **Todo error sale por `ApiError`.** Un `HTTPException` de FastAPI devuelto a mano produce
   `{"detail": ...}` y rompe el contrato en silencio, porque el cliente no valida la forma del
   error. `tests/test_api_contract.py` lo verifica.

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
