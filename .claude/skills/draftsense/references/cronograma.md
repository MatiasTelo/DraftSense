# Cronograma y estado real

> **Última actualización de este archivo: 07/11/2026.** Es el archivo de la skill que más se
> desactualiza. Al cerrar una semana, actualizar la columna Estado y la fecha de arriba.

Período 01/09/2026 – 19/11/2026, L–V 8:00–12:00. 200 hs planificadas sobre 228 hs de disponibilidad
efectiva (58 días hábiles menos el feriado del 12/10), o sea 28 hs de margen. La semana 6 tiene 16 hs
por ese feriado y la semana 12 tiene 8 hs por comprender sólo tres días hábiles.

## Las 12 semanas

| Sem. | Período | Entregable | Hs | Estado |
|---|---|---|---|---|
| 1 | 01/09 – 07/09 | Esquema de base de datos versionado y entorno de staging operativo | 20 | **cerrada** |
| 2 | 08/09 – 14/09 | API REST núcleo funcional con pruebas automatizadas | 20 | **cerrada** |
| 3 | 15/09 – 21/09 | Primer tipo de pregunta operativo de extremo a extremo | 20 | **cerrada** |
| 4 | 22/09 – 28/09 | Tipos de pregunta 2 y 3 operativos con feedback | 20 | **cerrada** — prueba a 360 px hecha el 16/09 |
| 5 | 29/09 – 05/10 | Módulos de sampling y calidad de datos integrados | 20 | **cerrada** — mergeada a `main` el 08/10 (PR #4) |
| 6 | 06/10 – 12/10 | Perfil, gamificación y versionado por parche · **Informe de Avance** | 16 | **cerrada** el 11/10 — correcciones del 05/10 (PR #5) y versionado por parche en la rama `semana-6-versionado-y-gamificacion`; la gamificación no necesitó ajuste |
| 7 | 13/10 – 19/10 | Aplicación desplegada en producción con panel de administración | 20 | **en curso** — panel como app local (ADR-025) en la rama `semana-7-panel-admin-local`, sin mergear; producción y worker pendientes por decisión del 21/10 |
| 8 | 20/10 – 26/10 | Piloto en curso y tipos de pregunta 4 y 5 operativos | 16 | **tipos cerrados** el 29/10 en la rama `semana-8-9-tipos-4-5-y-agregacion`, sin mergear; **el piloto queda para el final**, en los servidores del laboratorio (decisión del alumno) |
| 9 | 27/10 – 02/11 | Pipeline de agregación y CSV de features v1 | 16 | **cerrada** el 29/10 en la misma rama; el Informe de Calidad de Datos pasa a la semana 10 con el doc 27 |
| 10 | 03/11 – 09/11 | Módulo de validación e Informe de Calidad de Datos | 12 | **cerrada** el 07/11 en la rama `semana-10-validacion-y-calidad`, sin mergear; con dos correcciones de la prueba del alumno (idioma y feedback) |
| 11 | 10/11 – 16/11 | Segunda oleada de recolección y exportación final de los CSV | 12 | pendiente |
| 12 | 17/11 – 19/11 | Documentación técnica integrada y transferencia · **Informe Final** | 8 | pendiente |

## Qué cambió respecto del cronograma firmado

El cronograma del Informe Inicial asigna a la **semana 10** un "constructor de features por partida"
y a la **semana 11** los "CSV finales de features de campeón y de partida". **ADR-005 eliminó esa
línea de trabajo.** Las semanas 10 y 11 pasan a reforzar la validación de confiabilidad y la segunda
oleada de recolección, que es donde está el verdadero cuello de botella del proyecto.

Esto hay que registrarlo en el Informe de Avance de la semana 6.

**La semana 4 implementa el tipo 2 y sólo la variante 1v1 del tipo 3.** La 2v2 queda en la
semana 8, junto al tipo 4, como fija `docs/20-tipos-de-pregunta.md` §8: el cronograma dice «tipos 2
y 3» y el documento es el que manda. Para el Informe de Avance también: ADR-018 (textos de los
tipos 2 y 3 en el backend) y ADR-019 (roles desde el snapshot, porque los provisorios estaban mal en
38 de 58 campeones del tier 1).

**La semana 5, para el Informe de Avance.** Se implementó lo que el Informe Inicial pone en esa
semana —sampling adaptativo, honeypots, test-retest, deduplicación y trust score— con estas
decisiones, que el Informe de Avance tiene que registrar:

- **ADR-020:** el retest lo marca el servidor, que guarda la respuesta original pendiente en
  `respondents`; las cadencias y la honeypot pendiente también viven ahí (migración `0003`). La
  prueba de punta a punta en staging (17/09) encontró que la precarga del frontend producía
  honeypots dobles, cadencias estiradas y preguntas repetidas. Se corrigió con la honeypot
  pendiente y con **un parámetro nuevo y opcional en el contrato**, `queued`: los ids que el
  cliente tiene en cola.
- **ADR-021:** los puentes del grafo se materializan como una cadena de k−1 por dimensión. En
  staging son 421.
- **Los cuatro jobs existen pero se disparan por CLI**; la programación periódica sigue en la
  semana 7, con el despliegue.
- **Huecos de la especificación que se cerraron** (notas del 16/09 en 21 y 22): cobertura en los
  tipos 2 y 3, rol del 1v1 pesado por pares, piso de 40 intentos antes de retirar una honeypot
  (clave nueva `quality.honeypot_min_attempts`), *straightlining* contado por tipo, patrones
  degenerados recalculados desde cero, recarga conservadora del catálogo, y el fallback de
  explotación a exploración.
- **Catálogo de 34 honeypots** desde Data Dragon 16.17.1, aprobado por el alumno. `waveclear` quedó
  sin honeypots, igual que `scaling` y `pick`. **Falta la revisión de Marinozi antes de la
  semana 7.**
- **La mezcla ±5 de 21 §11 se mide recién con los seis tipos** (semana 8): con tres, la regla de
  variedad baja la proporción del tipo 1 a alrededor del 53 %.

**La semana 6 empezó con las correcciones de la reunión del lunes 05/10 con Marinozi**, que el
Informe de Avance también tiene que registrar:

- **ADR-022: el tipo 1 es un ranking de cinco campeones** que se guarda como diez comparaciones
  (tabla `rankings`, `responses.ranking_id`, migración `0004`). Par ancla elegido como antes + tres
  al azar; honeypot = el ancla; retest = el par de las puntas; pares ya contestados se ignoran; un
  ranking cuenta como una respuesta (`services/submissions.py`); fuera del *straightlining*.
  Frontend: `DimensionRankingCard` con `@dnd-kit`.
- **ADR-023: la salida por campeón son cuatro CSV largos** (`champion_dimensions`, `peak_timing`,
  `champion_lane_strength`, `champion_traits`), sin `synergy_mean`, y `duo_features` con `role_a` /
  `role_b`. La métrica pasa a **19 magnitudes por campeón**. Sustituye esa parte de ADR-005.
- **Mensaje nuevo para los primeros en responder**: *"There aren't enough answers yet to show how
  the community compares."* debajo de *"You're one of the first to answer this"*.
- **Docs:** 20 y 26 pasan a v2, `examples/` regenerado (v2), notas fechadas el 08/10 en 01, 02, 03,
  11, 12, 21, 22, 23, 25 y 30.
- **Tests:** backend 238 contra un Postgres 17 local en Docker (antes 222), frontend 80 (antes 77).
  Prueba manual a 360 px en Chrome contra la base local: la tarjeta entra sin scroll, filas de 52 px,
  el reordenamiento por teclado y por puntero funciona, el ranking guardó 10 filas con el mismo
  `ranking_id` y el mensaje nuevo aparece. Bundle 79 KB gzip.
- **Staging todavía no tiene la migración `0004`.** Aplicarla antes de usar la rama ahí.

**El cierre de la semana 6, 11/10/2026**, en la rama `semana-6-versionado-y-gamificacion`:

- **Gamificación: sin ajuste.** Lo implementado en las semanas 2 y 3 ya cumple
  `23-gamificacion.md`, y CA-303 y CA-310 a CA-313 tienen tests. Decisión del alumno.
- **Versionado por parche, ADR-024:** registrar un parche y activarlo pasan a ser pasos distintos.
  - `seed-champions` y `seed-pick-rate` ya **no** activan (`patches.register`).
  - El comando nuevo `activate-patch` (`services/patches.py`) rechaza un parche sin snapshot de
    pick rate o sin honeypots activas, salvo `--force`, y audita en `admin_audit`.
  - Las respuestas en vuelo se aceptan con el parche de su pregunta, y la honeypot y el retest
    pendientes de otro parche se descartan, como ya hacía el sampler.
  - Notas fechadas el 11/10 en 02 (CU-06), 12 §2 y 21 §8, y en el `README.md`.
- **Tests:** backend 248 (antes 238, 10 nuevos en `test_patches.py`) contra un Postgres 17 local
  en Docker; frontend sin cambios, 80. Prueba manual del flujo CU-06 por CLI contra la misma base.
- **Staging no se tocó.** No hay migración nueva, y el 16.17 tendría que seguir vigente porque lo
  activaron los seeds viejos: verificarlo con `GET /health` antes de usar la rama ahí. Sigue
  faltando la migración `0004`.
- **El Informe de Avance no se tocó** en este cierre. Sigue diciendo que el versionado por parche
  queda pendiente (§13).

**La semana 7, 21/10/2026**, en la rama `semana-7-panel-admin-local` (sale de `main` con el PR #6):

- **ADR-025, pedido de Marinozi:** la administración es una **app local del servidor del
  laboratorio** (`admin/backend` FastAPI + `admin/frontend` React), sólo en `127.0.0.1:5000`, **sin
  clave**, conectada directo a la base con `admin/.env`. La API pública **no** tiene `/admin/*`:
  se quitaron `X-Admin-Key`, `require_admin_key` y `DS_ADMIN_KEY`. Interfaz en español.
- **`24-panel-admin.md` a v1**: diez vistas, contrato interno, auditoría, CA-605 a CA-612. Notas
  fechadas el 21/10 en 01 (RF-404 reformulado), 02, 03, 10, 11, 12 (§1.3 y §2.7 sin efecto), 21,
  22 y 30.
- Decisiones del alumno en la planificación: jobs **en segundo plano** (estado en memoria, `409`
  si ya corre), parámetros con **cualquier JSON válido**, volumen 7/30/90 días, histograma de 20
  intervalos, auditoría paginada de a 50, seeds elegidos de `infra/seeds/`, `D_n` sobre
  agregables, y el botón de CSV **deshabilitado** hasta la semana 9.
- **Migración `0005`**: `run_job` y `run_seed` en el `CHECK` de `admin_audit`. **Staging no la
  tiene** (tampoco la `0004`).
- Backend: `services/seeding.py` (el camino de los seeds, compartido por CLI y panel),
  `connectivity.edges` y `components` públicas. Los tokens de ADR-017 pasan a
  `frontend/src/tokens.css`, más los colores de los gráficos del panel.
- **Tests:** backend 249 (antes 248: CA-606), admin backend 51, admin frontend 12, frontend 80, todo
  contra un Postgres 17 local en Docker. Prueba manual por Chrome contra esa base: CU-06 entero
  desde el panel (58/38/77, 131 roles, 34 honeypots, 4 filas de auditoría), el job de conectividad
  con los 456 puentes de ADR-021, y CA-605 (la IP de la máquina rechaza la conexión).
- **Staging no responde desde el 21/10:** el pooler de Supabase devuelve `tenant/user ... not
  found`. Hay que revisar el proyecto antes de usarlo.
- **Pendiente de la semana 7:** el despliegue a producción y la programación periódica del worker,
  hasta que se confirme el servidor del laboratorio.

**Las semanas 8 y 9, 29/10/2026**, en la rama `semana-8-9-tipos-4-5-y-agregacion` (sale de `main`
después del PR #7). **El piloto y el lanzamiento público quedan fuera**: se hacen al terminar, en
los servidores del laboratorio. Decisiones del alumno, todas registradas:

- **ADR-026:** el rol de cada campeón de una dupla en `questions.role_a … role_d` (migración
  `0006`, que también trae el `CHECK` del tipo 5 y `exports.params`).
- **ADR-027:** el tipo 5 exige al menos un atributo (sustituye CA-207).
- **ADR-028:** español en toda la interfaz con un selector EN/ES y `lang` en `GET
  /questions/next`. Traducciones propuestas por Claude y aprobadas por el alumno (neutro, «tú»).
- Precisiones en notas del 29/10: tipo 4 sólo tier 1 y contexto proporcional a sus pares; cobertura
  por (campeón, contexto); variedad por tipo y mezcla por variante; *straightlining* del 2v2 con el
  1v1, del tipo 4 propio, sin el tipo 5; feedback del tipo 5 por atributo que no suma al
  `agreement_rate`; pool del export, filas de bot por unión, MM propio y descarte con el grafo
  partido (25 §8.2).
- **Pipeline** en `aggregation/` (`python -m aggregation.run`), con job de CI propio. **Sin
  Informe de Calidad de Datos, bootstrap por respondedor ni segmentos**: son de la semana 10.
- **Panel:** *Generar CSV* habilitado, en segundo plano, con descarga verificada por SHA-256
  (`trigger_export`, 24 §3.9).
- **Seed sintética** `draftsense seed-synthetic-responses` (sólo base local): seed 42 sobre el
  16.17, 400 respondedores 70/20/10, unas 145 000 respuestas. Todas las preguntas de pico,
  atributos, 1v1 y las 450 de duplas con ≥ 20 respuestas; 58/58 campeones `solid` en las 8
  dimensiones; 32 respondedores bajo el umbral de trust. Corrida completa B = 2000 en ≈ 2,5 min,
  **mismo SHA-256 en dos corridas** (CA-408) y la verdad recuperada con ρ de 0,91 a 0,98.
- **Tests:** backend 286, aggregation 35, admin backend 55 (54 contra la base sembrada: ver la
  skill `draftsense-backend`), frontend 92, admin frontend 13. Bundle 82 KB gzip.
- **Prueba manual a 360 px, 29/10**, con Chrome (iframe de 360 px) contra la base de Docker
  sembrada: la landing y el juego en español con el selector, las tarjetas de 2v2, tipo 4 y tipo
  5, el feedback del tipo 5 («Coincides con la comunidad en 3 de 7 atributos», calculado bien) y el
  de soporte bajo. Sin scroll horizontal y todo lo que se toca mide 44 px o más. Encontró «Acerca
  de» partido en dos líneas en el pie y se corrigió.
- **Pendiente:** el piloto, al final, en los servidores del laboratorio.

**La semana 10, 07/11/2026**, en la rama `semana-10-validacion-y-calidad` (sale de `main` después
del PR #8). Decisiones del alumno, todas registradas:

- **`docs/27-validacion-confiabilidad.md` a v1.** Alfa de Krippendorff para **los cinco tipos**, con
  umbrales 0,800 / 0,667 que **sólo se reportan**; test-retest, honeypots y trust por horas sobre los
  no marcados **sin filtro de trust**; el cruce honeypot–retest por honeypot; cuartiles y ρ para el
  trust por horas; «cobertura por par» definida; el informe en **español**.
- **El bootstrap por respondedor se calcula, pero la decisión de 25 §4.7 queda para el piloto**
  (nota del 07/11 en 25 §4.7).
- **ADR-029:** cambiar de idioma **traduce** la cola (`GET /questions/queued`, 12 §2.8) en vez de
  descartarla. Sustituye ADR-028 §5.
- **ADR-030:** el feedback dura **4 s** y se saltea con un toque, `Enter` o `Espacio`; sin aviso.
- **Pipeline:** `aggregation/quality/` y el paso 7 que escribe el informe. Los seis CSV no cambian
  de hash: verificado contra el código de `main` con los mismos parámetros sobre la seed. La
  corrida completa con B = 2000 pasó de ≈ 2,5 a ≈ 10–11 min.
- **Panel:** la descarga sirve el informe como `text/markdown`.
- **Tests:** backend 293 (antes 286), aggregation 46 (antes 35), admin backend 55, frontend 103
  (antes 92), admin frontend 13, contra el Postgres 17 de Docker. Bundle 82 KB gzip.
- **Prueba manual a 360 px, 07/11**, con Chrome contra la base de Docker: el ranking reordenado
  sigue igual al pasar a ES; el feedback dura 4 007 ms sin tocar, se cierra con un toque y con
  `Enter`. Encontró que `Enter` no salteaba con el foco en el *Confirm* deshabilitado, y se corrigió.
- **Hallazgo de la seed sintética para revisar:** salvo el pico (0,769), todas las magnitudes dan
  alfa «no confiable» (0,09 a 0,34).
- **Los CSV de la base de Docker ya no dan los SHA-256 registrados el 29/10** con los mismos
  parámetros, tampoco con el código de `main`: cambió algo en la base desde entonces, no el código.

**La semana 3 adelantó `/me` y `/leaderboard`**, que el cronograma ponía en la semana 6: el backend
ya las exponía desde la semana 2 y la barra inferior de `/play` las necesita para no quedar con dos
destinos muertos. La semana 6 queda entonces con el versionado por parche, el ajuste de
gamificación y el Informe de Avance, que es su carga real en 16 horas.

## Estado real del repositorio

Al 16/09/2026:

- Rama `main`, remoto `https://github.com/MatiasTelo/DraftSense.git`.
- **Semana 1:** monorepo, CI de tres jobs (backend con Postgres 17 real, frontend con presupuesto
  de bundle, docs), esquema con migración inicial reversible, seeder de campeones desde Data Dragon
  con snapshot de respaldo, andamiaje del frontend, y la documentación técnica de las olas 1 a 3.
- **Semana 2:** los **siete endpoints públicos** (`/health`, `POST /sessions`,
  `POST /sessions/onboarding`, `GET /questions/next`, `POST /responses`, `GET /me`,
  `GET /leaderboard`) sobre una estructura en cuatro capas (ADR-015), la migración `0002` que
  cerró el desvío entre el esquema documentado y el implementado, los seeds de `app_settings`,
  alias y pick rate, y **50 tests**.
- **El pool ya está sembrado:** snapshot de lolalytics del parche 16.17, con 58 campeones en
  tier 1, 38 en tier 2 y 77 en tier 3 (ADR-016).
- **Semana 3:** el circuito completo del tipo 1. En el backend, el job
  `refresh_question_stats` (service más comando de CLI) que puebla `answer_counts`, `exposure_count`
  y `entropy`, y con eso el feedback de consenso deja de ser siempre `null`; **13 tests nuevos, 63
  en total**. En el frontend, Tailwind v4 con los tokens del canvas de Claude Design (ADR-017), el
  cliente HTTP, los dos stores de Zustand, las **cinco pantallas** y los ocho estados de
  `30-ux-flujos.md` §8; **44 tests de componente**. Bundle en 60 KB gzip de los 200 del presupuesto.
- Se resolvieron dos inconsistencias entre el maquetado y el esquema: se sacó el botón *Fill* de
  `/start` (punto 4 de `25-agregacion.md` §12) y los once rangos de `VALID_RANKS` se muestran
  completos en vez del chip colapsado *Master+*. Ambas anotadas en `30-ux-flujos.md` §4.
- **Semana 4:** los tipos 2 (`peak_timing`) y 3 variante 1v1 (`lane_matchup`) de punta a punta.
  Documentación primero: ADR-018, ADR-019 y notas fechadas en 20, 12, 11, 21 (con la errata del
  upsert de §2.2) y 03. En el backend: la unión discriminada, `/questions/next` con las 3 primeras
  de tipo 1 y la mezcla 50/20/15 renormalizada, la mediana del feedback del tipo 2, el job para los
  tres tipos, los roles desde el snapshot (`seed-pick-rate` y el comando nuevo `sync-roles`) y
  `pydantic>=2.13`; **52 tests nuevos, 115 en total**. En el frontend: `PeakTimingCard`,
  `LaneMatchupCard`, el feedback de la mediana y el layout apilado, `key` por tarjeta y candado
  contra el doble envío; **23 tests nuevos, 67 en total**. Bundle en 63 KB gzip.
- **Staging, 16/09:** se corrió `sync-roles --patch 16.17` (roles de 131 campeones; el tier 1
  quedó con 13 top, 13 jungle, 13 mid, 16 adc y 12 support) y `refresh-question-stats`. Todavía no
  había preguntas de tipo 2 ni 3 materializadas, así que ninguna quedó armada con roles
  provisorios.
- **Cierre de la semana 4, 16/09:** prueba a 360 px con Chrome (iframe de 360 px sobre staging,
  porque la ventana no baja de ese ancho). `PeakTimingCard` y `LaneMatchupCard` pasan: sin scroll
  horizontal, opciones de 52 px, slider de 44. Aparecieron tres objetivos táctiles de pantallas de
  la semana 3 por debajo de 44 px —el `?` de ayuda, `Skip` y las pestañas del leaderboard— y se
  corrigieron sin cambiar lo que se ve (nota en `30-ux-flujos.md` §9; 4 tests nuevos, 71 en total).
  No hay canvas de Claude Design de las tarjetas 2 y 3 en el repo: se maquetaron con los wireframes
  de 20 §3 y §4.1 y los tokens existentes.
- **Semana 5:** el sampler completo y el módulo de calidad. Documentación primero: ADR-020,
  ADR-021 y notas fechadas en 03, 10, 11, 12, 21 y 22. En el backend:
  - la migración `0003` (cuatro columnas);
  - `sampler.py` (prioridad, ε con fallback en los dos sentidos, variedad, puentes, cadencias);
  - `trust.py`, `honeypots.py`, `retests.py`, `degenerate.py`, `fingerprints.py`,
    `connectivity.py`, `trust_check.py` y `aggregable.py`;
  - `POST /responses` con retest y trust sincrónicos;
  - `refresh_question_stats` con cobertura, retests excluidos y retiro de honeypots;
  - la carga del catálogo (`seed-honeypots`) y cinco comandos nuevos.

  - `queued` en `GET /questions/next` y en la cola del frontend.

  **107 tests nuevos, 222 en total**, que pasan contra un Postgres 17 local limpio y otro sembrado
  como staging (la versión de 215 también pasó contra staging, en 70 minutos por la latencia). En
  el frontend, tests que fijan la posición de las opciones (el *straightlining* depende de eso) y
  el envío de `queued`: 77 en total.
- **Staging, 16 y 17/09:** migración `0003` (re-aplicada el 17 con la cuarta columna), la clave
  nueva, las 34 honeypots, `refresh-question-stats`, 421 puentes, los dos jobs diarios y
  `verify-trust-scores` sin divergencias en 37 respondedores. Prueba de punta a punta con Chrome a
  360 px sobre el respondedor de prueba, en tres tandas. La primera encontró honeypots dobles y
  cadencias corridas, y la segunda, preguntas repetidas (`409`). La tercera, ya con `queued` como
  lista de ids, dio honeypots en 116, 127 y 137 y el retest en 139, ningún `409`, trust igual a la
  fórmula y ningún campo de calidad en las respuestas de la API. El respondedor de prueba quedó con
  145 respuestas en staging. La suite completa contra staging corrió sobre la versión anterior a
  `queued`; la actual pasó en local y los tests de esquema, contra staging.
  Contra staging, desde esta máquina, un `POST` tarda de 3 a 5 s y un lote hasta 8 s: es la red
  (en local, 23 y 54 ms). El presupuesto de latencia se mide en la semana 7, con la API y la base
  en la misma región.
- **`aggregation/` tiene el pipeline desde el 29/10** (semana 9).
- **Lo que NO tiene el backend todavía:** la programación del worker (con el despliegue, pendiente
  desde el 21/10: los cuatro jobs se disparan a mano por CLI o desde el panel). La variante 2v2 y
  los tipos 4 y 5 llegaron el 29/10.
- **El motor de tarjetas tiene los cinco tipos desde el 29/10.**
- **Las dos brechas que quedaban para la semana 5 se cerraron:** el rol salteado ya queda en el
  log (`logging`, 21 §8), y el sorteo del 1v1 pesa el rol por su cantidad de pares (errata de
  21 §4.4).
- **Sin nivel E2E todavía.** CA-501 y CA-505 se verifican punta a punta en la semana 7, junto con
  `31-plan-de-pruebas.md`, que es el documento que define los niveles y sigue pendiente.

## Entregables académicos

| Cuándo | Qué |
|---|---|
| Semana 6 (06/10 – 12/10) | **Informe de Avance** + informes de los dos tutores |
| Semana 12 (17/11 – 19/11) | **Informe Final** + informes de los dos tutores + transferencia |

Los redacta la skill `pps-informes`, que vive en `.claude/skills/` de la carpeta de la PPS (fuera de
este repo, porque los informes también están fuera).
