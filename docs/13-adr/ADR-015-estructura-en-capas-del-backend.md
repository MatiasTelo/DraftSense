# ADR-015 — Estructura en capas del backend

> Estado: **aceptada** · Fecha: 09/09/2026

## Contexto

La semana 2 escribe el primer código de aplicación del proyecto: siete endpoints públicos sobre una
capa de datos que ya existe. Las semanas 3 a 8 agregan cinco tipos de pregunta, el sampler, el
módulo de calidad, la gamificación y el panel de administración **sobre esa misma base**.

[ADR-007](ADR-007-fastapi-python.md) fijó el stack, no la organización del código. Sin una
convención escrita, cada semana resuelve de nuevo dónde va la lógica: el primer endpoint la pone en
el router, el tercero descubre que necesita reusarla, y para la semana 6 la misma regla de negocio
está escrita en tres lugares que se desincronizan.

Hay además dos decisiones concretas que conviene cerrar de una vez porque reaparecen en cada
endpoint: cómo se traduce una excepción al formato de error del contrato, y dónde vive el rate limit.

## Decisión

**Cuatro capas, con una regla de dependencia que va en un solo sentido:**
`routers → services → models`, y `schemas` transversal a los tres primeros.

| Capa | Responsabilidad | Lo que NO hace |
|---|---|---|
| `app/routers/` | Declarar la ruta, sus parámetros, sus dependencias y su código de estado. Un router es una traducción HTTP: no toma decisiones | Ninguna consulta a la base, ninguna regla de negocio |
| `app/services/` | Toda la lógica: consultas, transacciones, reglas de `docs/`. Recibe una `AsyncSession` y tipos del dominio | No conoce `Request`, `Response`, cookies ni códigos HTTP |
| `app/schemas/` | Los modelos Pydantic de entrada y salida, **con los campos listados uno por uno** | No se derivan de un modelo ORM con `from_attributes` sobre la clase entera |
| `app/models/` | El esquema, ya escrito | — |

Más dos módulos transversales: `app/errors.py`, con la excepción de aplicación y sus manejadores, y
`app/dependencies.py`, con las dependencias de FastAPI que resuelven identidad y autorización.

**Un service no importa nada de `fastapi`.** Es la regla que hace verificable todo lo demás: si un
service necesita `Request` para hacer su trabajo, la lógica está en la capa equivocada.

### Los errores se emiten desde una sola excepción

`app/errors.py` define `ApiError(code, message, status, field=None)` y el manejador que la serializa
al sobre de `docs/12-api.md` §3:

```json
{ "error": { "code": "answer_shape_mismatch", "message": "…", "field": "answer" } }
```

Se registran tres manejadores más, para que **ninguna respuesta de error se escape del formato**:
`RequestValidationError` de Pydantic → `422 validation_error`; `IntegrityError` de la violación del
índice único parcial → `409 duplicate_response`; `DBAPIError` de conexión → `503
database_unavailable`.

Los códigos son los tabulados en §3 y no se inventan nuevos sin agregarlos ahí primero.

### El rate limit se cuenta sobre el índice que ya existe

40 respuestas por minuto y 1 500 por día, contando filas de `responses` sobre
`responses_by_respondent`, sin Redis ni contador en memoria. Está fijado en `docs/12-api.md` §4 y se
registra acá porque es la decisión que más tienta a "optimizar" con infraestructura.

## Alternativas consideradas

- **Todo en los routers.** Es lo natural para siete endpoints y lo que la documentación de FastAPI
  muestra en sus ejemplos. Se descartó por lo que viene después: el sampler de la semana 5 lo
  consumen `GET /questions/next` y los tests, y el trust score lo tocan `POST /responses`, tres jobs
  de fondo y el panel. Esa lógica no puede vivir dentro de un manejador HTTP.
- **Un repositorio por tabla** (`app/repositories/`). Aísla SQLAlchemy detrás de una interfaz y
  permitiría cambiar de ORM. Es una capa de indirección que se paga en cada consulta para una
  portabilidad que nadie va a usar: el esquema **depende** de Postgres —enums nativos, `jsonb`,
  índices parciales, `NULLS NOT DISTINCT`— y cambiar de motor implicaría rehacerlo entero.
- **Arquitectura hexagonal completa**, con puertos, adaptadores y entidades de dominio separadas de
  los modelos ORM. Correcto para un sistema con varias fuentes de datos y reglas de negocio densas;
  acá habría dos representaciones de cada tabla y un mapeo entre ellas, para un sistema cuya única
  fuente de datos es una base y cuyo pipeline estadístico **ya comparte los modelos** con la API.
- **Middleware para el rate limit** en vez de resolverlo dentro del service de respuestas. Se
  descartó porque el límite es por `respondent_id`, que sólo se conoce después de resolver la cookie,
  y porque las cabeceras `X-RateLimit-*` sólo las lleva `POST /responses`: un middleware global
  tendría que saber a qué rutas no aplicarse.

## Consecuencias

- Una regla de negocio se prueba **sin levantar HTTP**: los tests del sampler, de las rachas y del
  trust score llaman al service directamente. Sólo los tests de contrato pasan por el cliente.
- El panel de administración de la semana 7 y los jobs de fondo reutilizan los mismos services que
  la API. Un job es un `main()` que abre una sesión y llama a un service.
- Hay que sostener la disciplina del sobre de error: un `HTTPException` de FastAPI devuelto a mano
  produce `{"detail": …}` y **rompe el contrato en silencio**, porque el cliente no lo valida. Se
  cubre con un test que recorre los errores documentados y verifica la forma de todos.
- Los schemas de salida se escriben a mano, campo por campo. Es más verboso que serializar el modelo
  ORM, y es deliberado: es lo que garantiza que `trust_score`, `session_token_hash`,
  `fingerprint_hash`, `is_honeypot` y `expected_answer` no salgan nunca (`12-api.md` §1.4, RF-207).
