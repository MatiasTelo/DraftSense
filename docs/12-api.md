# 12 — Contrato de la API REST

> Estado: **v1** · Última revisión: 31/08/2026

Base: `https://api.draftsense.dev/api/v1` · OpenAPI autogenerada en `/docs`.

Este documento es el contrato entre el frontend y el backend. La especificación OpenAPI se genera
sola desde los modelos Pydantic; **si divergen, manda el código y este documento está desactualizado**.

---

## 1. Principios

### 1.1 El servidor arma los textos, el cliente los muestra

La API devuelve el enunciado **ya renderizado**, con los nombres de campeón sustituidos:
`"Who wins this lane at 10 minutes?"`, `"Syndra wins hard"`. El cliente no compone strings ni conoce
plantillas.

Esto pone la internacionalización en un solo lugar —el servidor, que ya lee `dimensions.label_en` y
`label_es` de la base— y permite agregar el español sin tocar el frontend
([ADR-010](13-adr/ADR-010-interfaz-en-ingles.md)).

### 1.2 La forma de la pregunta es una unión discriminada por `type`

Los cinco tipos comparten una envoltura común y difieren en el cuerpo. El campo `type` es el
discriminante, lo que se mapea directo a un *tagged union* de TypeScript del lado del cliente.

Toda opción que representa una entidad comparable lleva un arreglo `champions`, tenga uno o dos
elementos. Así el cliente renderiza duplas y campeones individuales con el mismo componente.

### 1.3 Autenticación

Ninguna para el usuario final. La sesión anónima viaja en la cookie `ds_session`:
`HttpOnly; Secure; SameSite=Lax; Max-Age=15552000` (180 días).

Los endpoints `/admin/*` requieren el header `X-Admin-Key`.

### 1.4 Lo que nunca sale de la API

- `is_honeypot` y `expected_answer` — exponerlos invalidaría el mecanismo entero.
- `trust_score` — mostrarlo invitaría a jugar con la métrica.
- `session_token_hash`, `fingerprint_hash` y cualquier dato de identificación.

---

## 2. Endpoints

| Método | Ruta | Para qué |
|---|---|---|
| `POST` | `/sessions` | Crear o revalidar la sesión anónima |
| `POST` | `/sessions/onboarding` | Guardar rango, rol y horas declaradas |
| `GET` | `/questions/next` | Pedir el próximo lote de preguntas |
| `POST` | `/responses` | Registrar una respuesta |
| `GET` | `/me` | Perfil y progreso del respondedor |
| `GET` | `/leaderboard` | Tabla de posiciones |
| `GET` | `/admin/stats` | Métricas del panel de administración |
| `POST` | `/admin/exports` | Disparar una corrida de agregación |
| `GET` | `/health` | Sonda de salud |

---

### 2.1 `POST /sessions`

Crea una sesión anónima. **Idempotente**: si llega con una cookie válida, no crea nada nuevo y sólo
actualiza `last_seen`.

**Request:** sin cuerpo. El cliente envía en el header `X-Client-Fingerprint` un hash calculado
localmente a partir de user-agent y resolución de pantalla; el servidor lo combina con un hash de
la IP antes de almacenarlo.

**`201 Created`** (o `200 OK` si la sesión ya existía), con `Set-Cookie: ds_session=…`

```jsonc
{
  "respondent_id": "3f2a7c19-1d4e-4b8a-9f02-6c1e5b7a0d33",
  "onboarding_seen": false,
  "answers_count": 0,
  "current_streak": 0,
  "best_streak": 0
}
```

---

### 2.2 `POST /sessions/onboarding`

```jsonc
// request — los tres campos son opcionales; null = prefirió no decir
{
  "declared_rank": "platinum",
  "declared_main_role": "support",
  "declared_hours_bucket": "5-15"
}
```

```jsonc
// 200 OK
{ "onboarding_seen": true }
```

Omitir el onboarding es igualmente una respuesta: el cliente llama con los tres campos en `null`,
lo que marca `onboarding_seen = true` y evita volver a preguntar. Los datos son variables de
segmentación para el análisis de estabilidad por rango, **nunca criterio de calidad**: el rango
declarado no es verificable ([ADR-001](13-adr/ADR-001-sin-autenticacion.md)).

---

### 2.3 `GET /questions/next?count=5`

Devuelve el próximo lote según el sampler. Se piden de a lotes para que la interfaz no espere entre
tarjeta y tarjeta.

**Parámetros:** `count` entero, 1–10, por defecto 5.

**`200 OK`** — un arreglo `questions` cuyos elementos siguen una de estas cinco formas.

#### Envoltura común

```jsonc
{
  "question_id": 88412,
  "type": "pairwise_dimension",
  "prompt": "Who has more engage?",
  "help": { "label": "Engage", "text": "Starting fights on your terms." }
}
```

`help` es lo que despliega el ícono `?`. Es `null` sólo cuando el tipo no lo necesita.

#### `pairwise_dimension`

```jsonc
{
  "question_id": 88412,
  "type": "pairwise_dimension",
  "prompt": "Who has more engage?",
  "help": { "label": "Engage", "text": "Starting fights on your terms." },
  "options": [
    { "key": "a", "champions": [
        { "id": 12, "key": "Alistar", "name": "Alistar",
          "image_url": "https://ddragon.leagueoflegends.com/cdn/16.20.1/img/champion/Alistar.png" }
    ]},
    { "key": "b", "champions": [
        { "id": 157, "key": "Yasuo", "name": "Yasuo",
          "image_url": "https://ddragon.leagueoflegends.com/cdn/16.20.1/img/champion/Yasuo.png" }
    ]},
    { "key": "unknown", "label": "Not sure", "champions": [] }
  ]
}
```

#### `peak_timing`

```jsonc
{
  "question_id": 91002,
  "type": "peak_timing",
  "prompt": "When does Kayle peak?",
  "help": { "label": "Power spike",
            "text": "The point in the game where this champion is at their strongest compared to everyone else." },
  "subject": { "champions": [ { "id": 10, "key": "Kayle", "name": "Kayle", "image_url": "…" } ] },
  "slider": {
    "min": 0, "max": 40, "step": 1, "default": 20, "unit": "min",
    "marks": [
      { "at": 0,  "label": "laning" },
      { "at": 15, "label": "mid game" },
      { "at": 30, "label": "late game" }
    ]
  }
}
```

#### `lane_matchup` — variante 1v1

```jsonc
{
  "question_id": 77310,
  "type": "lane_matchup",
  "prompt": "Who wins this lane at 10 minutes?",
  "help": { "label": "Lane matchup", "text": "Assume equal skill and no jungle interference." },
  "context": { "role": "mid", "label": "MID" },
  "sides": [
    { "key": "a", "champions": [ { "id": 134, "key": "Syndra", "name": "Syndra", "image_url": "…" } ] },
    { "key": "b", "champions": [ { "id": 238, "key": "Zed",    "name": "Zed",    "image_url": "…" } ] }
  ],
  "options": [
    { "key": "a_strong", "label": "Syndra wins hard" },
    { "key": "a_slight", "label": "Syndra wins slightly" },
    { "key": "even",     "label": "Even" },
    { "key": "b_slight", "label": "Zed wins slightly" },
    { "key": "b_strong", "label": "Zed wins hard" }
  ]
}
```

#### `lane_matchup` — variante 2v2

Misma forma; `sides` lleva dos campeones por lado y las etiquetas hablan de parejas.

```jsonc
{
  "question_id": 77988,
  "type": "lane_matchup",
  "prompt": "Which bot lane wins at 10 minutes?",
  "help": { "label": "Bot lane matchup",
            "text": "Which pair beats the other in lane. Not about how well each pair works together — that's a different question." },
  "context": { "duo_context": "bot", "label": "BOT" },
  "sides": [
    { "key": "a", "champions": [ {"id": 51, "key": "Caitlyn", …}, {"id": 99,  "key": "Lux", …} ] },
    { "key": "b", "champions": [ {"id": 360,"key": "Samira",  …}, {"id": 111, "key": "Nautilus", …} ] }
  ],
  "options": [
    { "key": "a_strong", "label": "Top pair wins hard" },
    { "key": "a_slight", "label": "Top pair wins slightly" },
    { "key": "even",     "label": "Even" },
    { "key": "b_slight", "label": "Bottom pair wins slightly" },
    { "key": "b_strong", "label": "Bottom pair wins hard" }
  ]
}
```

#### `duo_synergy`

```jsonc
{
  "question_id": 64881,
  "type": "duo_synergy",
  "prompt": "Which duo works better together?",
  "help": { "label": "Synergy",
            "text": "Ignore who they're up against. Which two complement each other better?" },
  "context": { "duo_context": "bot", "label": "BOT" },
  "sides": [
    { "key": "pair_1", "champions": [ {…}, {…} ] },
    { "key": "pair_2", "champions": [ {…}, {…} ] }
  ],
  "options": [
    { "key": "pair_1",  "label": "Top pair" },
    { "key": "similar", "label": "About the same" },
    { "key": "pair_2",  "label": "Bottom pair" }
  ]
}
```

#### `trait_multiselect`

```jsonc
{
  "question_id": 55120,
  "type": "trait_multiselect",
  "prompt": "What does Sett do well?",
  "subtitle": "Pick all that apply.",
  "help": null,
  "subject": { "champions": [ { "id": 875, "key": "Sett", "name": "Sett", "image_url": "…" } ] },
  "traits": [
    { "code": "engage",        "label": "Engage",        "help": "Starts fights on their own terms." },
    { "code": "poke",          "label": "Poke",          "help": "Wears enemies down from range." },
    { "code": "pick",          "label": "Pick",          "help": "Catches out and kills isolated targets." },
    { "code": "peel",          "label": "Peel",          "help": "Keeps divers off their carries." },
    { "code": "front_to_back", "label": "Front to back", "help": "Wants a straight teamfight, tanks in front." },
    { "code": "dive",          "label": "Dive",          "help": "Jumps past the front line onto the back line." },
    { "code": "split_push",    "label": "Split push",    "help": "Pressures a side lane instead of grouping." }
  ]
}
```

---

### 2.4 `POST /responses`

```jsonc
// request
{ "question_id": 88412, "answer": { "choice": "a" }, "response_time_ms": 2140 }
```

La forma de `answer` depende del tipo de la pregunta (ver
[`11-modelo-de-datos.md`](11-modelo-de-datos.md) §5). El servidor la valida contra el tipo real de
`question_id`, no contra lo que declare el cliente.

```jsonc
// 201 Created
{
  "recorded": true,
  "feedback": {
    "consensus": { "a": 0.74, "b": 0.19, "unknown": 0.07 },
    "agreed_with_majority": true,
    "sample_size": 312
  },
  "progress": {
    "answers_count": 18,
    "current_streak": 7,
    "best_streak": 31,
    "agreement_rate": 0.81
  }
}
```

**`feedback` es `null` cuando `sample_size < 20`.** El cliente muestra entonces *"you're one of the
first to answer this"*, para no anclar las respuestas de los primeros usuarios sobre ruido
([ADR-012](13-adr/ADR-012-sampler-uniforme-en-arranque-en-frio.md)).

`consensus` sale del campo denormalizado `questions.answer_counts`, refrescado cada 15 minutos. Puede
estar levemente desactualizado; es irrelevante para un mensaje motivacional y evita un `GROUP BY` en
el camino crítico.

Para `peak_timing` el consenso no es una distribución de opciones sino la mediana observada:

```jsonc
"feedback": { "consensus_median": 26, "your_answer": 27, "sample_size": 88 }
```

---

### 2.5 `GET /me`

```jsonc
{
  "answers_count": 143,
  "current_streak": 12,
  "best_streak": 31,
  "agreement_rate": 0.78,
  "coverage": {
    "pairwise_dimension": 96,
    "peak_timing": 21,
    "lane_matchup": 18,
    "duo_synergy": 5,
    "trait_multiselect": 3
  },
  "rank_percentile": 0.91,
  "alias": "brave-poro-4417"
}
```

`trust_score` **no se expone**.

---

### 2.6 `GET /leaderboard?window=week`

**Parámetros:** `window` ∈ `day` | `week` | `all`, por defecto `week`.

```jsonc
{
  "window": "week",
  "generated_at": "2026-10-24T14:03:11Z",
  "entries": [
    { "rank": 1, "alias": "brave-poro-4417", "answers_count": 412, "is_you": false },
    { "rank": 2, "alias": "calm-baron-0091", "answers_count": 389, "is_you": true }
  ]
}
```

Top 50. Los respondedores con `is_flagged = true` quedan fuera. El alias nunca es un identificador
real; su generación y moderación se especifican en [`23-gamificacion.md`](23-gamificacion.md).

---

### 2.7 Endpoints de administración

Requieren `X-Admin-Key`. Sin el header o con clave inválida: `401`.

**`GET /admin/stats`** — volumen de respuestas por día y tipo, cobertura por campeón y dimensión,
distribución del trust score, estado de conectividad del grafo por dimensión, respondedores marcados.

**`POST /admin/exports`** — dispara una corrida de agregación y registra las filas en `exports`.

```jsonc
// request
{
  "patch_window": "16.18..16.20",
  "min_trust": 0.30,
  "decay_halflife_days": 21,
  "bootstrap_samples": 2000
}
// 202 Accepted
{ "run_id": "…", "status": "queued" }
```

Responde `202` y no `201` porque la corrida lleva minutos: el cliente consulta el estado por
`GET /admin/exports/{run_id}`.

**`GET /health`** — verifica conectividad a la base y devuelve el parche vigente. Sin autenticación.

```jsonc
{ "status": "ok", "current_patch": "16.20", "db": "ok" }
```

---

## 3. Errores

Formato uniforme, compatible con el manejador de excepciones de FastAPI:

```jsonc
{
  "error": {
    "code": "answer_shape_mismatch",
    "message": "answer does not match the shape expected for question type 'peak_timing'",
    "field": "answer"
  }
}
```

| HTTP | `code` | Cuándo |
|---|---|---|
| `400` | `answer_shape_mismatch` | El `answer` no corresponde al tipo de la pregunta |
| `400` | `unknown_trait_code` | Un código de `traits` no existe o está inactivo |
| `400` | `invalid_parameter` | Parámetro de query fuera de rango |
| `401` | `admin_key_required` | Falta o es inválido `X-Admin-Key` |
| `404` | `question_not_found` | `question_id` inexistente |
| `409` | `duplicate_response` | Ya respondió esa pregunta y no está marcada como retest |
| `422` | `validation_error` | Error de esquema de Pydantic |
| `429` | `rate_limit_exceeded` | Ver §4 |
| `503` | `database_unavailable` | La base no responde |

**Sobre el `409`:** lo impone el índice único parcial
`responses (respondent_id, question_id) WHERE is_retest_of IS NULL`. La restricción vive en la base,
no en el código, así que una carrera entre dos requests simultáneos falla correctamente en vez de
insertar dos filas.

---

## 4. Rate limiting

Ventana deslizante por `respondent_id` y por hash de IP:

| Límite | Valor |
|---|---|
| Por minuto | 40 respuestas |
| Por día | 1 500 respuestas |

El límite es holgado para una persona —una respuesta cada 5–10 segundos equivale a unas 10 por
minuto— y corta el scripting trivial.

Todas las respuestas de `POST /responses` incluyen:

```
X-RateLimit-Limit: 40
X-RateLimit-Remaining: 33
X-RateLimit-Reset: 1761315791
```

Al excederse, `429` con `Retry-After` en segundos.

Se implementa **contando sobre el índice `responses (respondent_id, created_at DESC)`**, sin Redis
ni contador en memoria. Además de ahorrar infraestructura, evita que el límite se reinicie en cada
despliegue.

---

## 5. CORS y cabeceras

| Cabecera | Valor |
|---|---|
| `Access-Control-Allow-Origin` | `https://draftsense.dev` (y el dominio de preview en staging) |
| `Access-Control-Allow-Credentials` | `true` — necesario para que viaje la cookie |
| `Access-Control-Allow-Headers` | `Content-Type, X-Client-Fingerprint` |

`Allow-Origin` **no es `*`**: con credenciales, el comodín no está permitido por la especificación,
y además no hay razón para que otro origen consuma esta API.

---

## 6. Versionado

La versión va en la ruta: `/api/v1`. Dentro de `v1` sólo se admiten cambios **aditivos**: agregar
campos opcionales a una respuesta, agregar endpoints, agregar valores a un enum de salida que el
cliente ya trate con un caso por defecto.

Cualquier cambio que rompa a un cliente existente —quitar un campo, cambiar un tipo, cambiar la
semántica de un valor— abre `/api/v2`.

Durante la práctica el único cliente es la SPA propia y ambos se despliegan juntos, así que el
riesgo real es bajo. La disciplina se mantiene igual porque el laboratorio podría consumir la API
después de la transferencia.
