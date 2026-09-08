# El contrato REST

**El contrato completo está en `docs/12-api.md`.** Acá están los principios y las trampas; el
request y el response de cada endpoint se leen del documento, no de esta skill.

## Los principios

1. **El servidor arma los textos, el cliente los muestra** (§1.1). La API devuelve el enunciado ya
   renderizado, con los nombres de campeón sustituidos: `"Who wins this lane at 10 minutes?"`. El
   cliente no compone strings ni conoce plantillas. Así la internacionalización queda en un solo
   lugar —el servidor, que ya lee `dimensions.label_en` y `label_es`— y agregar el español no toca
   el frontend.
2. **La pregunta es una unión discriminada por `type`** (§1.2). Los cinco tipos comparten envoltura
   y difieren en el cuerpo. **Toda opción que representa una entidad comparable lleva un arreglo
   `champions`, tenga uno o dos elementos**, para que el cliente renderice duplas y campeones con el
   mismo componente. No "optimices" mandando un objeto suelto cuando hay un solo campeón.
3. **Sin autenticación de usuario** (§1.3). Cookie `ds_session`:
   `HttpOnly; Secure; SameSite=Lax; Max-Age=15552000`. Los `/admin/*` van con header `X-Admin-Key`.
4. **Versión en la ruta: `/api/v1`** (§6). Dentro de `v1` sólo cambios **aditivos**: campos
   opcionales, endpoints nuevos, valores nuevos en un enum que el cliente ya trate con un caso por
   defecto. Quitar un campo o cambiar un tipo es `v2`.

## Lo que nunca sale de la API (§1.4)

Es un requisito, no una preferencia:

- `is_honeypot` y `expected_answer` — exponerlos invalidaría el mecanismo entero.
- `trust_score` — mostrarlo invitaría a jugar con la métrica (RF-207).
- `session_token_hash`, `fingerprint_hash` y cualquier dato de identificación.

Al escribir un schema de respuesta de Pydantic, listá los campos explícitamente. **No serialices un
modelo ORM entero.**

## Los trece endpoints

| Método | Ruta |
|---|---|
| `POST` | `/sessions` · `/sessions/onboarding` · `/responses` |
| `GET` | `/questions/next` · `/me` · `/leaderboard` · `/health` |
| `GET` | `/admin/stats` |
| `POST` | `/admin/exports` · `/admin/patches/{patch_id}/activate` · `/admin/respondents/{id}/flag` |
| `PATCH` | `/admin/champions/pool-tier` · `/admin/settings/{key}` |

## Errores

Formato uniforme, compatible con el manejador de excepciones de FastAPI:

```jsonc
{ "error": { "code": "answer_shape_mismatch", "message": "...", "field": "answer" } }
```

Los códigos están tabulados en §3. Dos que importan al implementar:

- **`409 duplicate_response`** lo impone el índice único parcial
  `responses (respondent_id, question_id) WHERE is_retest_of IS NULL`. **La restricción vive en la
  base, no en el código**, para que una carrera entre dos requests simultáneos falle correctamente en
  vez de insertar dos filas. No lo reimplementes con un `SELECT` previo: capturá la violación.
- **`422 validation_error`** es el de Pydantic; el resto se emiten a mano con el formato de arriba.

## Rate limiting (§4)

40 respuestas por minuto y 1 500 por día, en ventana deslizante por `respondent_id` y por hash de IP.

**Se implementa contando sobre el índice `responses (respondent_id, created_at DESC)`, sin Redis ni
contador en memoria.** Además de ahorrar infraestructura, evita que el límite se reinicie en cada
despliegue. Toda respuesta de `POST /responses` lleva `X-RateLimit-Limit`, `X-RateLimit-Remaining` y
`X-RateLimit-Reset`; al excederse, `429` con `Retry-After` en segundos.

## CORS (§5)

`Access-Control-Allow-Origin` es el dominio concreto, **nunca `*`**: con
`Allow-Credentials: true` el comodín no está permitido por la especificación, y la cookie tiene que
viajar. El origen se configura con `DS_CORS_ORIGIN`. Headers permitidos:
`Content-Type, X-Client-Fingerprint`.
