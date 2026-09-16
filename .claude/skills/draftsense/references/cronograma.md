# Cronograma y estado real

> **Última actualización de este archivo: 16/09/2026.** Es el archivo de la skill que más se
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
| 4 | 22/09 – 28/09 | Tipos de pregunta 2 y 3 operativos con feedback | 20 | **en curso** — código, docs y staging listos; falta la prueba manual a 360 px |
| 5 | 29/09 – 05/10 | Módulos de sampling y calidad de datos integrados | 20 | pendiente |
| 6 | 06/10 – 12/10 | Perfil, gamificación y versionado por parche · **Informe de Avance** | 16 | pendiente |
| 7 | 13/10 – 19/10 | Aplicación desplegada en producción con panel de administración | 20 | pendiente |
| 8 | 20/10 – 26/10 | Piloto en curso y tipos de pregunta 4 y 5 operativos | 16 | pendiente |
| 9 | 27/10 – 02/11 | Pipeline de agregación y CSV de features v1 | 16 | pendiente |
| 10 | 03/11 – 09/11 | Módulo de validación e Informe de Calidad de Datos | 12 | pendiente |
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
- **Pendiente de la semana 4:** la prueba manual de las dos tarjetas nuevas a 360 px. No hay canvas
  de Claude Design de las tarjetas 2 y 3 en el repo: se maquetaron con los wireframes de 20 §3 y
  §4.1 y los tokens existentes.
- **`aggregation/` está vacía.** El paquete se implementa en la semana 9.
- **Lo que NO tiene el backend todavía:** el sampler completo con la regla de variedad (semana 5 —
  hoy `/questions/next` sortea el tipo con pesos y la pregunta uniforme), honeypots, retests y
  trust score (semana 5), los `/admin/*` (semana 7), los otros tres jobs de fondo y la
  programación del worker (semana 7: hoy `refresh_question_stats` se dispara a mano).
- **Del motor de tarjetas faltan la variante 2v2 del tipo 3 y los tipos 4 y 5**, todos de la
  semana 8. `QuestionCard` devuelve `null` para esos dos tipos.
- **Brechas conocidas para la semana 5:** `21-sampler.md` §8 pide registrar en el log el rol
  salteado, y el backend no tiene logging; §4.4 llama uniforme a «rol y después par», que sólo lo
  es si los roles tienen el mismo tamaño.
- **Sin nivel E2E todavía.** CA-501 y CA-505 se verifican punta a punta en la semana 7, junto con
  `31-plan-de-pruebas.md`, que es el documento que define los niveles y sigue pendiente.

## Entregables académicos

| Cuándo | Qué |
|---|---|
| Semana 6 (06/10 – 12/10) | **Informe de Avance** + informes de los dos tutores |
| Semana 12 (17/11 – 19/11) | **Informe Final** + informes de los dos tutores + transferencia |

Los redacta la skill `pps-informes`, que vive en `.claude/skills/` de la carpeta de la PPS (fuera de
este repo, porque los informes también están fuera).
