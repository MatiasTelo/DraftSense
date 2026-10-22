# 24 — Panel de administración

> Estado: **v1** · Ola 3 · Semana 7 · Última revisión: 21/10/2026

La administración de DraftSense es una **aplicación aparte, que corre en local en el servidor del
laboratorio**, sin clave ni login ([ADR-025](13-adr/ADR-025-app-de-administracion-local.md)). Este
documento fija qué muestra, qué permite hacer, el contrato REST interno entre su frontend y su
backend, y los criterios de aceptación de RF-401 a RF-405.

---

## 1. Forma de la aplicación

| Pieza | Carpeta | Qué es |
|---|---|---|
| Backend | `admin/backend/` | FastAPI, paquete `draftsense_admin`. Se conecta directo a Postgres y reutiliza `backend/app/` (services, models, seeds) |
| Frontend | `admin/frontend/` | SPA Vite + React + TypeScript + Tailwind v4, con los tokens de `frontend/src/tokens.css`, compartidos con la SPA pública ([ADR-017](13-adr/ADR-017-tailwind-como-sistema-de-estilos.md)) |

- **Escucha sólo en `127.0.0.1`.** El script de arranque (`admin/run.ps1` y `admin/run.sh`) fija el
  host; el puerto es configurable, por defecto `5000`. Como segunda barrera, por si alguien lo
  levanta a mano con otro host, el backend responde `403 local_only` a todo pedido que no venga
  de una dirección de loopback.
- **Un solo proceso en el servidor.** El backend sirve el build del frontend (`admin/frontend/dist`)
  como estáticos; en desarrollo, `vite dev` hace de proxy hacia el backend.
- **Credenciales.** El DSN sale de `admin/.env` (`DS_DATABASE_URL`), que no se versiona. Hay un
  `admin/.env.example` sin secretos.
- **Idioma.** La interfaz está en español (ADR-025 §6). El código, los identificadores y las claves
  del contrato, en inglés.
- **Sin estado propio, salvo los jobs en curso.** Todo vive en la base y recargar la página no
  pierde nada. La única excepción es el estado de un job que está corriendo (§3.7), que vive en la
  memoria del proceso: si se reinicia el proceso, el job se corta y su corrida no queda auditada.

## 2. Navegación

Una barra lateral fija con las vistas, en este orden. El orden sigue la frecuencia de uso durante
el piloto: lo que se mira todos los días arriba, lo que se hace una vez por parche abajo.

| # | Vista | Ruta | Requerimiento |
|---|---|---|---|
| 1 | Resumen | `/` | RF-401 |
| 2 | Conectividad y tier | `/conectividad` | RF-402, 21 §7.2 |
| 3 | Cobertura | `/cobertura` | RF-401 |
| 4 | Calidad | `/calidad` | RF-401, 22 §6.3 |
| 5 | Pool | `/pool` | RF-403, RF-604 |
| 6 | Parámetros | `/parametros` | RF-606 |
| 7 | Jobs | `/jobs` | 10 §4 |
| 8 | Parches y seeds | `/parches` | RF-403, CU-06 |
| 9 | Exportaciones | `/exportaciones` | RF-403, CU-08 |
| 10 | Auditoría | `/auditoria` | RF-405 |

Arriba de todo, en todas las vistas, una franja con el **parche vigente** (o «sin parche vigente»
en rojo) y la hora de la última carga de datos de la vista, con un botón *Actualizar*. Las vistas
no se refrescan solas: el panel lo mira una persona, no una pantalla de monitoreo.

```
┌─────────────────┬────────────────────────────────────────────────────────┐
│ DraftSense      │ Parche vigente: 16.17      Datos de las 10:42 [Actualizar]│
│ Administración  ├────────────────────────────────────────────────────────┤
│                 │                                                        │
│ ▸ Resumen       │   (contenido de la vista)                              │
│   Conectividad  │                                                        │
│   Cobertura     │                                                        │
│   Calidad       │                                                        │
│   Pool          │                                                        │
│   Parámetros    │                                                        │
│   Jobs          │                                                        │
│   Parches       │                                                        │
│   Exportaciones │                                                        │
│   Auditoría     │                                                        │
└─────────────────┴────────────────────────────────────────────────────────┘
```

El panel se usa sobre todo en el monitor del servidor, pero **el layout también funciona angosto**:
por debajo de 768 px la barra lateral se pliega en un menú, y las tablas anchas (cobertura, pool)
scrollean dentro de su contenedor, nunca la página entera.

## 3. Vistas

### 3.1 Resumen

Cuatro tarjetas y un gráfico.

- **Respuestas totales** del parche vigente, y de ellas cuántas son **agregables** (los filtros de
  [`25-agregacion.md`](25-agregacion.md) §1, vía `services/aggregable.py`).
- **Respondedores** con al menos una respuesta en el parche vigente, y cuántos están marcados.
- **Envíos de hoy** (un ranking del tipo 1 cuenta como uno, ADR-022, `services/submissions.py`).
- **Dimensiones conectadas**: `k de 8`, el mismo número que la vista 3.2.
- **Volumen por día y por tipo**: barras apiladas con un selector de ventana de **7, 30 o 90 días**
  (por defecto 30), una serie por tipo de pregunta, contando envíos. El día se corta en la zona de `gamification.streak_timezone`.

### 3.2 Conectividad y tier

Lo que decide si el piloto produce datos utilizables (CU-07).

**Tabla por dimensión activa**: código, cantidad de componentes conexas, tamaño de la componente
más grande, puentes marcados pendientes, y un estado `conectada` / `partida`. Las componentes se
calculan **en lectura**, con las mismas aristas que el job `check_graph_connectivity`
(`services/connectivity.py`): pares del tipo 1 del parche vigente con respuesta `a` o `b` que entra
a la agregación, sobre los campeones del pool habilitado. **Esta vista no marca ni materializa
puentes**; eso lo hace el job (vista 3.7).

**Los dos indicadores de [`21-sampler.md`](21-sampler.md) §7.2**, juntos en un recuadro:

| Indicador | Cómo se calcula | Umbral |
|---|---|---|
| Mediana de `D_n` del tier 1 | Para cada campeón de `pool_tier = 1` y cada una de las 8 dimensiones activas, `D_n` = cantidad de respuestas agregables del tipo 1 del parche vigente con `choice ∈ {a, b}` en las que participa el campeón en esa dimensión (la definición de `score_n` de 25 §5.1 y 26 §2.4). Se toma la mediana de esas celdas | `≥ 25` |
| Dimensiones conectadas | Las de la tabla de arriba con una sola componente | `≥ 6 de 8` |

Cada indicador muestra su valor, el umbral y un tilde o una cruz. Debajo, una sola línea:
**«Se cumple la condición para habilitar el tier 2»** sólo si se cumplen los dos; si no, cuál falta.
El panel **no habilita el tier por su cuenta**: la acción está en la vista 3.6
(`sampler.enabled_pool_tiers`).

### 3.3 Cobertura

Una matriz **campeón × dimensión** del pool habilitado, con `D_n` en cada celda (la misma cuenta
de 3.2), coloreada en tres bandas según los umbrales de dimensiones de
[`26-esquema-de-salida.md`](26-esquema-de-salida.md) §2.4 por `n`: `≥ 25`, `≥ 10`, `< 10`. Es una
aproximación del `support_level` que va a tener el export —el ancho del IC no se puede saber sin
ajustar Bradley-Terry— y la leyenda lo dice.

Filtros: tier y rol. Orden: por la `D_n` mínima del campeón, ascendente, para que arriba queden los
que más faltan.

### 3.4 Calidad

- **Distribución del trust score** de los respondedores con al menos una respuesta en el parche
  vigente: histograma de **veinte intervalos de 0.05** sobre `[0, 1]`, con una línea vertical en
  `export.min_trust`. Es el único lugar del sistema donde se ve el trust, y sólo como distribución
  ([`22-calidad-de-datos.md`](22-calidad-de-datos.md) §7).
- **Respondedores marcados**: tabla con el identificador abreviado (8 caracteres), `answers_count`,
  `first_seen`, `last_seen` y un botón *Desmarcar*.
- **Marcar o desmarcar a mano** un respondedor por su identificador completo, con un motivo
  obligatorio. Es para el falso positivo de la deduplicación por huella (22 §6.3). El motivo va al
  payload de la auditoría.

### 3.5 Pool

Tabla de campeones activos: nombre, roles, `pool_tier`, y su posición en el último snapshot de pick
rate del parche vigente. Selección múltiple y un control *Mover a tier* `1 | 2 | 3` con
confirmación. Es el `UPDATE` de ADR-006, no un despliegue.

### 3.6 Parámetros

Todas las claves de `app_settings`, agrupadas por bloque (`sampler.`, `quality.`, `gamification.`,
`export.`, `aggregation.`), con su valor actual, `updated_at` y `updated_by`, y la descripción del
seed (`infra/seeds/app_settings.yaml`) como ayuda.

Editar una clave abre un editor del valor en JSON con confirmación. Reglas:

- **No se crean claves** desde el panel: una clave nueva llega con el código que la usa, en un seed.
- **Se acepta cualquier JSON válido.** No hay un esquema por clave en ningún documento, y la
  decisión del 21/10/2026 es no inventarlo: la responsabilidad del valor es de quien lo edita. Por
  eso la confirmación muestra el valor actual y el nuevo lado a lado.
- `updated_by` queda en `admin`.
- La API pública cachea `app_settings` 60 segundos (11 §3.12): el cambio tarda a lo sumo eso en
  verse. La vista lo avisa.

### 3.7 Jobs

Los cuatro jobs de [`10-arquitectura.md`](10-arquitectura.md) §4, cada uno con su botón *Ejecutar*,
la hora de su última corrida desde el panel (de `admin_audit`) y su resultado:

| Job | Service | Resultado que se muestra |
|---|---|---|
| `refresh_question_stats` | `question_stats.refresh` | Preguntas recalculadas, respuestas, medianas de cobertura, honeypots retiradas |
| `check_graph_connectivity` | `connectivity.check` | Componentes y puentes por dimensión, dimensiones conectadas |
| `detect_degenerate_patterns` | `degenerate.detect` | Respondedores revisados y con contadores nuevos. Campo *ventana en horas*, por defecto 24 |
| `flag_duplicate_fingerprints` | `fingerprints.flag_duplicates` | Huellas sobre el umbral, respondedores marcados |

Los jobs corren **en segundo plano**, en una tarea del proceso admin: *Ejecutar* responde enseguida
con un `run_id` y la vista consulta el estado cada 2 segundos hasta que termina (`running` →
`succeeded` o `failed`). **Un job no corre dos veces a la vez**: mientras corre, su botón está
deshabilitado y un segundo pedido responde `409 job_running`. Los cuatro sí pueden correr en
paralelo entre sí, cada uno con su sesión de base. La fila de auditoría se escribe **al terminar
bien**, con el resultado; un job que falla muestra el error y no audita. El estado de las corridas
vive en memoria (§1) y se conserva sólo la última por job. La programación periódica sigue
pendiente con el despliegue (decisión del 21/10/2026).

### 3.8 Parches y seeds

**Tabla de parches**: versión, `released_at`, vigente, si tiene snapshot de pick rate, cantidad de
honeypots activas. Es lo que `services/patches.missing_for` verifica.

**Los cuatro pasos de CU-06**, en ese orden y numerados en pantalla:

1. **Catálogo de campeones** (`seed_champions`): versión del parche, versión de Data Dragon
   (opcional, por defecto la última), fecha de salida (opcional) y, si el CDN no responde, usar el
   respaldo `infra/seeds/ddragon_champions_snapshot.json`.
2. **Snapshot de pick rate** (`seed_pick_rate`): versión del parche, un archivo
   `infra/seeds/pick_rate_*.csv` elegido de una lista, fuente (por defecto `lolalytics`), URL de la
   captura (obligatoria), fecha de captura (obligatoria), fecha de salida y notas (opcionales).
3. **Honeypots** (`seed_honeypots`): versión del parche, un archivo `infra/seeds/honeypots_*.yaml`
   elegido de una lista, y *reactivar retiradas* (`force`).
4. **Activar** (`patches.activate`): versión del parche y *forzar* (`force`). Sin forzar, si faltan
   el snapshot o las honeypots, el panel muestra cada faltante y no activa (ADR-024, alternativo C
   de CU-06).

**Los archivos se eligen de los que ya están en `infra/seeds/` del servidor; el panel no sube
archivos.** Antes de escribir, cada seed valida su archivo con la misma función que `check-seeds`, y
los errores se muestran tal cual. Los avisos (nombres del snapshot que no están en el catálogo,
roles sin campeones, honeypots salteadas) se muestran debajo del resultado.

Activar y forzar piden confirmación con el texto de lo que va a pasar («las preguntas nuevas van a
tomar el parche X; las respuestas anteriores conservan el suyo»).

### 3.9 Exportaciones

El formulario de CU-08 con sus cuatro parámetros —ventana de parches, umbral de confianza, vida
media del decaimiento y remuestreos del bootstrap—, precargados con los valores actuales de
`app_settings` (`export.min_trust`, `aggregation.decay_halflife_days`,
`aggregation.bootstrap_samples`) y la ventana en el parche vigente.

**El botón *Generar CSV* está deshabilitado** con la leyenda «Disponible cuando esté el pipeline de
agregación (semana 9)». No hay endpoint detrás todavía. Debajo, la lista de corridas anteriores
leída de `exports` (vacía hasta la semana 9).

### 3.10 Auditoría

Todas las filas de `admin_audit`, de la más nueva a la más vieja, **paginadas de a 50 y sin tope**:
fecha y hora, `action` y el `payload` desplegable. Filtro por `action`. Sólo lectura.

## 4. Auditoría de cada acción

Toda acción que escribe deja **una** fila en `admin_audit` (RF-405). Las acciones del panel la
escriben en la misma transacción que el cambio. Los jobs y los seeds no pueden: sus services ya
hacen commit por su cuenta, así que la fila se escribe al terminar bien, en una transacción propia. La migración `0005` amplía el `CHECK` de `admin_audit.action` con `run_job` y `run_seed`.

| Acción del panel | `action` | `payload` |
|---|---|---|
| Activar parche | `activate_patch` | `{patch_id, version, previous}` (ADR-024; lo escribe `patches.activate`) |
| Mover campeones de tier | `set_pool_tier` | `{champion_ids, pool_tier, updated}` |
| Cambiar `sampler.enabled_pool_tiers` | `set_enabled_tiers` | `{key, value, previous}` |
| Cambiar cualquier otra clave | `set_setting` | `{key, value, previous}` |
| Marcar o desmarcar respondedor | `flag_respondent` | `{respondent_id, flagged, previous, reason}` |
| Ejecutar un job | `run_job` | `{job, params, result}` |
| Cargar un seed | `run_seed` | `{seed, patch, file, params, result}` |
| Generar CSV (semana 9) | `trigger_export` | se define con el pipeline |

Una acción que no cambia nada —activar el vigente, mover a un tier que ya tienen, poner el mismo
valor, marcar a un marcado— **no audita**, como ya hace ADR-024. Un job o un seed **siempre**
audita, porque correrlo es en sí el hecho que se quiere registrar. Una acción que falla no audita.

## 5. Contrato interno

Prefijo `/api`. JSON en los dos sentidos. Sin autenticación (ADR-025). Los errores usan el mismo
sobre que la API pública ([`12-api.md`](12-api.md) §3), `{"error": {"code", "message", "field"}}`,
con un campo opcional más, `details`: la lista de problemas cuando hay más de uno.
Este contrato **no es público** y puede cambiar con el panel; no entra en `12-api.md`.

| Método | Ruta | Vista | Respuesta / cuerpo |
|---|---|---|---|
| `GET` | `/api/overview` | 3.1, franja | `?days=7\|30\|90` → parche vigente, totales, volumen por día y tipo |
| `GET` | `/api/connectivity` | 3.2 | Tabla por dimensión + los dos indicadores |
| `GET` | `/api/coverage` | 3.3 | Matriz campeón × dimensión con `D_n` |
| `GET` | `/api/quality` | 3.4 | Histograma de trust, `min_trust`, marcados |
| `POST` | `/api/respondents/{id}/flag` | 3.4 | `{flagged, reason}` → `{respondent_id, is_flagged}` |
| `GET` | `/api/champions` | 3.5 | Campeones activos con tier, roles y posición en el snapshot |
| `PATCH` | `/api/champions/pool-tier` | 3.5 | `{champion_ids, pool_tier}` → `{updated}` |
| `GET` | `/api/settings` | 3.6 | Las claves con valor, fechas y descripción |
| `PATCH` | `/api/settings/{key}` | 3.6 | `{value}` → `{key, value, previous}` |
| `GET` | `/api/jobs` | 3.7 | Los cuatro jobs con su última corrida (estado, inicio, fin, resultado o error) |
| `POST` | `/api/jobs/{job}` | 3.7 | `{params}` → `202 {run_id, job, status: "running"}` |
| `GET` | `/api/jobs/{job}/runs/{run_id}` | 3.7 | `{run_id, job, status, started_at, finished_at, result, error}` |
| `GET` | `/api/patches` | 3.8 | Parches con sus faltantes |
| `GET` | `/api/seeds/files` | 3.8 | Archivos de `infra/seeds/` por tipo |
| `POST` | `/api/seeds/champions` | 3.8 | Paso 1 → resultado y avisos |
| `POST` | `/api/seeds/pick-rate` | 3.8 | Paso 2 → resultado y avisos |
| `POST` | `/api/seeds/honeypots` | 3.8 | Paso 3 → resultado y avisos |
| `POST` | `/api/patches/{version}/activate` | 3.8 | `{force}` → `{patch_id, version, previous, changed}` |
| `GET` | `/api/exports` | 3.9 | Corridas de `exports` y los valores por defecto del formulario |
| `GET` | `/api/audit` | 3.10 | `?action=&page=` (50 por página) → `{items, page, total}` |

Códigos: `400 invalid_parameter` (cuerpo inválido, JSON inválido, clave inexistente, archivo fuera
de `infra/seeds/`), `404` (respondedor, parche, job o corrida inexistente), `409 patch_not_ready`
(activar sin forzar con faltantes, con cada faltante en `details`), `409 job_running` (el job ya
está corriendo), `422 seed_invalid` (el archivo no pasa la validación, con cada problema en
`details`).

**El nombre de archivo de un seed se valida contra la lista de `/api/seeds/files`**, nunca se usa
como ruta: un nombre con `/`, `\` o `..` es `400`.

## 6. Lo que el panel no hace

- No borra ni modifica respuestas (ADR-002). Ninguna acción toca `responses`.
- No muestra el trust de un respondedor individual, ni la huella, ni el hash del token.
- No crea claves de `app_settings` ni dimensiones ni atributos.
- No genera CSV hasta la semana 9.
- No programa los jobs: eso llega con el despliegue.

## 7. Criterios de aceptación

Completan los que [`03-criterios-aceptacion.md`](03-criterios-aceptacion.md) dejó para este
documento. `I` = integración (pytest contra Postgres), `M` = manual.

### CA-605 · El panel sólo atiende desde la máquina — RF-404 · `M`
**Dado** la app admin levantada con su script de arranque
**Cuando** se pide `http://<ip-del-servidor>:5000/` desde otra máquina de la red
**Entonces** la conexión es rechazada, y desde el propio servidor `http://127.0.0.1:5000/` responde.

### CA-606 · La API pública no tiene administración — RF-404 · `I`
**Dado** la API pública
**Cuando** se pide cualquier ruta `/api/v1/admin/...`
**Entonces** responde `404`, y la OpenAPI pública no lista ninguna ruta de administración.

### CA-607 · Las métricas de CU-07 — RF-401 · `I`
**Dado** un parche vigente con respuestas sembradas de tres tipos, dos respondedores marcados y una
honeypot contestada
**Cuando** se piden `/api/overview`, `/api/coverage` y `/api/quality`
**Entonces** el volumen por día y tipo cuenta envíos, la cobertura excluye la honeypot, los
retests, los marcados y los de trust bajo `export.min_trust`, y los dos marcados aparecen en la
lista.

### CA-608 · Conectividad e indicadores de tier — RF-402 · `I`
**Dado** respuestas del tipo 1 que dejan 5 dimensiones conectadas y una mediana de `D_n` de 30
**Cuando** se pide `/api/connectivity`
**Entonces** informa 5 de 8, la mediana 30, y que la condición del tier 2 **no** se cumple por la
conectividad; y la consulta no marca ni crea ninguna pregunta.

### CA-609 · Activar desde el panel es lo mismo que desde el CLI — RF-403 · `I`
**Dado** un parche sin honeypots
**Cuando** se pide activarlo sin forzar
**Entonces** responde `409 patch_not_ready` con el faltante, el vigente no cambia y no hay fila
nueva en `admin_audit`; forzando, se activa y hay una fila `activate_patch`.

### CA-610 · Jobs y seeds quedan auditados — RF-405 · `I`
**Dado** el panel
**Cuando** se ejecuta `refresh_question_stats`, se espera a que termine, y se carga el snapshot de
pick rate
**Entonces** hay una fila `run_job` y una `run_seed` con el resultado en el `payload`; y un segundo
pedido del mismo job mientras corre responde `409 job_running`.

### CA-611 · Un seed no sale de `infra/seeds/` — RF-403 · `I`
**Dado** el panel
**Cuando** se pide cargar un seed con el archivo `../backend/.env`
**Entonces** responde `400` y no lee nada.

### CA-612 · El botón de exportación espera al pipeline — RF-403 · `M`
**Dado** la vista Exportaciones antes de la semana 9
**Cuando** se la abre
**Entonces** el formulario muestra los valores de `app_settings` y *Generar CSV* está deshabilitado
con su leyenda.

CA-604 (tres acciones, tres filas) se verifica sobre los endpoints de esta app.

---

Ver el índice en [`README.md`](README.md) y las decisiones ya cerradas en [`13-adr/`](13-adr/).
