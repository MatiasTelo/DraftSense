# SQLAlchemy 2.0, Alembic y Postgres

El esquema completo —DDL, diccionario de datos, esquemas JSON de validación, índices y
migraciones— está en `docs/11-modelo-de-datos.md`. **Esa es la fuente de verdad**; los modelos ORM
la reflejan, y los tests verifican que no se separen.

## Las once tablas

`patches`, `champions`, `pick_rate_snapshots`, `pick_rate_entries`, `dimensions`, `traits`,
`respondents`, `questions`, `responses`, `aggregates`, `exports`.

`infra/check_docs.py` falla si alguna desaparece del DDL. Los modelos están repartidos en
`app/models/`: `catalog.py`, `collection.py`, `outputs.py`, `enums.py`, `base.py`.

## Base declarativa

`app/models/base.py` define `Base(DeclarativeBase)` con una `NAMING_CONVENTION` explícita:

```python
{"ix": "ix_%(table_name)s_%(column_0_N_name)s",
 "uq": "uq_%(table_name)s_%(column_0_N_name)s",
 "ck": "%(constraint_name)s",
 "fk": "fk_%(table_name)s_%(column_0_name)s",
 "pk": "pk_%(table_name)s"}
```

**No la toques.** Sin nombres deterministas, Alembic genera uno distinto en cada corrida y los
`downgrade()` no encuentran qué borrar. Los `CHECK` usan el nombre tal cual se declara, sin prefijo,
porque en este esquema todos se nombran a mano y ya llevan el nombre de la tabla
(`questions_shape`, `responses_answer_shape`): así el nombre real en Postgres coincide literalmente
con el del DDL documentado.

`utcnow()` devuelve `sa.text("now()")` para defaults del lado del servidor. Usar eso, no
`datetime.now()` de Python.

## Migraciones

- Una sola migración por ahora: `migrations/versions/0001_initial_schema.py`.
- **Toda migración debe ser reversible.** CI corre `alembic downgrade base` y después
  `alembic upgrade head`. Un `downgrade()` que no deshace todo rompe el build, incluidos los tipos
  enum nativos, que hay que dropear a mano.
- Alembic lee el DSN de `DS_DATABASE_URL` igual que la aplicación (ver `migrations/env.py`).
- `mypy` no revisa `migrations/versions/`, pero `ruff` sí revisa todo el backend.

## Postgres 15 o superior

El esquema usa cosas que no están en versiones anteriores. Desarrollo y CI corren sobre **17**.

- **`NULLS NOT DISTINCT`** en los índices únicos `questions_identity` y `aggregates_identity`. Es de
  Postgres 15 y **sqlglot todavía no lo modela**, así que `check_docs.py` los tiene en su lista de
  sentencias toleradas sin validar. Si agregás una sentencia que sqlglot no parsea, el check falla a
  propósito: hay que revisarla a mano y recién ahí sumarla a `UNPARSEABLE_BY_SQLGLOT`.
- Enums nativos, arrays, `jsonb` e índices parciales. Por eso el job de CI levanta un Postgres real:
  ninguna otra cosa valida la migración de verdad.
- `pgcrypto` como extensión.

## Append-only, garantizado por permisos

El rol `draftsense_app` tiene `INSERT` y `SELECT` sobre `responses`, y se le **revoca explícitamente
`UPDATE`, `DELETE` y `TRUNCATE`** (`docs/11-modelo-de-datos.md` §4). No es una convención del
código: es el motor el que lo impide. No escribas código que asuma que puede corregir una respuesta.

## Base de desarrollo — Supabase

Proyecto gratuito, **separado del de producción**: las respuestas de prueba no deben poder contaminar
el dataset que se le entrega al laboratorio.

Del panel hay que tomar la cadena del **Session pooler, puerto 5432**. Las otras dos no sirven:

| Opción | Por qué no |
|---|---|
| Direct connection (`db.<ref>.supabase.co`) | Sólo publica registro AAAA; no resuelve desde una red sin IPv6 |
| Transaction pooler (puerto 6543) | No admite sentencias preparadas y Alembic no puede correr contra él |

El DSN lleva `?ssl=require`, que es la opción de **asyncpg**. Los tests la traducen a `sslmode` para
psycopg, que es el driver sincrónico que usan las pruebas no async.

```
DS_DATABASE_URL=postgresql+asyncpg://usuario:clave@host:5432/basededatos?ssl=require
```

Va en `backend/.env`, que está en `.gitignore`. **Las credenciales nunca se escriben en un archivo
versionado, ni en una skill, ni en un comentario.**
