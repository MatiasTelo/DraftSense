# ADR-024 — Un parche se activa con un paso explícito, auditado y con precondiciones

> Estado: **aceptada** · Fecha: 11/10/2026

## Contexto

El crudo ya se versiona por parche ([ADR-004](ADR-004-ventana-de-parches-con-decaimiento.md)):
cada pregunta y cada respuesta llevan su `patch_id`, `questions_identity` lo incluye, y el sampler
sólo sirve preguntas del parche vigente. Lo que no estaba resuelto es **cómo se pasa de un parche
al siguiente**.

Hasta la semana 6 el parche vigente lo cambiaba un efecto lateral: `seed-champions` y
`seed-pick-rate` creaban el parche pedido **y lo marcaban como vigente**. Eso tenía tres problemas:

1. **El orden de los seeds decidía cuándo cambiaba el parche.** El primer `seed-champions --patch
   16.20` dejaba vigente un parche sin snapshot de pick rate ni catálogo de honeypots, y el sampler
   empezaba a materializar preguntas contra él en la petición siguiente.
2. **Un parche sin honeypots congela el trust.** Las honeypots son por parche
   ([`22-calidad-de-datos.md`](../22-calidad-de-datos.md) §3.3). Sin catálogo, ningún respondedor
   suma intentos y el trust de los nuevos queda en el valor inicial durante todo el parche.
3. **No quedaba rastro.** CU-06 pide que las acciones de catálogo dejen una fila en `admin_audit`
   (RF-405), y la activación por efecto lateral no la dejaba.

Además, ningún documento decía qué pasa con lo que está en vuelo cuando cambia el parche: la
pregunta que el cliente tiene en cola, la honeypot y el retest pendientes del respondedor.

## Decisión

**Activar un parche es un paso propio** (`activate-patch` en el CLI, y desde la semana 7 también
`POST /admin/patches/{patch_id}/activate`), y los dos usan el mismo service, `services/patches.py`.

- **Los seeds registran, no activan.** `seed-champions` y `seed-pick-rate` crean el parche si no
  existe y actualizan `released_at` si se pasa, pero no tocan `is_current`. El orden de CU-06 queda
  `seed-champions` → `seed-pick-rate` → `seed-honeypots` → `activate-patch`.
- **Precondiciones.** La activación falla si el parche no existe. También se rechaza si al parche le
  falta **un snapshot de pick rate** (una fila en `pick_rate_snapshots`) o **al menos una honeypot
  activa** (una fila de `questions` con `is_honeypot`). Cada faltante se informa por separado.
  `--force` activa igual: es para un entorno de prueba o una emergencia, no para el camino normal.
- **Auditada.** Cada activación deja una fila en `admin_audit` con `action = 'activate_patch'` y el
  payload `{patch_id, version, previous}`, con la forma de la respuesta de `12-api.md` §2.
  `previous` es `null` si no había parche vigente. Bajar el anterior, subir el nuevo y escribir la
  auditoría van en una sola transacción.
- **Activar el que ya está vigente no hace nada** y no deja auditoría, para que repetir el comando
  no llene `admin_audit` de filas sin cambio.
- **Lo que está en vuelo se acepta con el parche de la pregunta.** Una pregunta del parche anterior
  que el cliente tenía en cola y contesta después de la activación se registra normalmente:
  `responses.patch_id` se copia de la pregunta, así que la respuesta queda en el parche anterior.
  Lo mismo vale para un ranking del tipo 1 servido antes del cambio.
- **Lo pendiente de otro parche se descarta.** Si la honeypot o el retest pendientes del respondedor
  ([ADR-020](ADR-020-estado-de-cadencias-en-el-servidor.md)) son de otro parche, el primer lote
  después del cambio no los vuelve a servir y elige otros del parche vigente. Las cadencias no se
  reinician: siguen contando contra `answers_count`.

## Alternativas consideradas

- **Dejar que los seeds activen**, como hasta la semana 6. Es un paso menos, pero el parche cambia
  en el medio de la carga y sin rastro, que es justo lo que motivó la decisión.
- **Rechazar las respuestas en vuelo** con un error nuevo, para que ninguna respuesta posterior a la
  activación quede en el parche anterior. Exige un código de error más en el contrato y que el
  frontend descarte la cola. Lo que se gana es poco: son a lo sumo unas pocas respuestas por
  respondedor activo, y la ventana con decaimiento de ADR-004 ya combina parches cercanos. Perderlas
  sería tirar datos escasos.
- **Avisar y activar igual** cuando faltan el snapshot o las honeypots. Es el patrón de
  `seed-champions` con los roles, pero acá el efecto es silencioso y dura todo un parche: un trust
  congelado no se ve en ninguna pantalla hasta el Informe de Calidad de Datos.

## Consecuencias

- **El setup de un entorno nuevo suma un paso.** Sin `activate-patch` no hay parche vigente,
  `GET /health` devuelve `current_patch: null` y `GET /questions/next` devuelve un lote vacío.
- **El pool se actualiza antes que el parche.** `pool_tier` y `roles` viven en `champions` y no
  están versionados por parche. Como el snapshot del parche nuevo es requisito para activarlo, al
  cargarlo cambian el pool y los roles **mientras el parche anterior sigue vigente**. La ventana
  dura lo que se tarde entre `seed-pick-rate` y `activate-patch`, y ya existía antes de esta
  decisión. No se corrige acá.
- **Un parche nuevo arranca en frío.** Las preguntas son filas nuevas, así que vuelven a estar en
  cero `exposure_count`, `answer_counts` y los puentes, y un respondedor puede volver a contestar un
  par que ya contestó en el parche anterior. Es lo que se busca: la opinión se mide de nuevo contra
  el parche nuevo, y la agregación combina las dos con decaimiento.
- La auditoría se escribe aunque el panel de la semana 7 todavía no exista, con el mismo `action`
  que ya admite el `CHECK` de `admin_audit`.
