# 01 — Requerimientos

> Estado: **v1** · Última revisión: 31/08/2026

Requerimientos funcionales y no funcionales, numerados y priorizados. Cada uno tiene al menos un
criterio de aceptación verificable en [`03-criterios-aceptacion.md`](03-criterios-aceptacion.md).

**Prioridad (MoSCoW):** `M` imprescindible · `S` importante · `C` deseable · `W` fuera de esta
entrega.

---

## 1. Requerimientos funcionales

### RF-0xx — Sesión e identidad

| # | Requerimiento | Pr. |
|---|---|---|
| RF-001 | El sistema debe crear una sesión anónima sin requerir registro, identificada por una cookie `HttpOnly; Secure; SameSite=Lax` de 180 días | M |
| RF-002 | La creación de sesión debe ser idempotente: una petición con cookie válida no genera una identidad nueva | M |
| RF-003 | El sistema debe almacenar únicamente el hash SHA-256 del token de sesión, nunca el token en claro | M |
| RF-004 | El sistema debe registrar una huella de navegador irreversible (SHA-256 de user-agent, hash de IP y resolución) con el único fin de deduplicar | M |
| RF-005 | El sistema debe permitir declarar rango, rol principal y horas semanales de juego, y debe permitir omitir los tres | M |
| RF-006 | El sistema no debe almacenar email, nombre, dirección IP en claro ni identificador de cuenta de Riot | M |

### RF-1xx — Preguntas y respuestas

| # | Requerimiento | Pr. |
|---|---|---|
| RF-101 | El sistema debe entregar preguntas en lotes configurables de 1 a 10 | M |
| RF-102 | El sistema debe implementar el tipo 1, comparación pareada por dimensión funcional, sobre 8 dimensiones | M |
| RF-103 | El sistema debe implementar el tipo 2, slider de minuto de pico de poder, en rango 0–40 | M |
| RF-104 | El sistema debe implementar el tipo 3 variante 1v1, matchup de línea al minuto 10 con 5 niveles de margen, en top, mid y adc | M |
| RF-105 | El sistema debe implementar el tipo 3 variante 2v2, enfrentamiento entre duplas de bot con la misma escala de 5 niveles | S |
| RF-106 | El sistema debe implementar el tipo 4, comparación de sinergia entre dos duplas del mismo contexto | S |
| RF-107 | El sistema debe implementar el tipo 5, multi-selección sobre los 7 atributos originales del laboratorio | S |
| RF-108 | El sistema debe validar la forma de cada respuesta contra el tipo real de la pregunta, y rechazar las que no correspondan | M |
| RF-109 | El sistema debe registrar el tiempo de respuesta en milisegundos | M |
| RF-110 | El sistema debe impedir que un respondedor conteste dos veces la misma pregunta, salvo que sea un retest deliberado | M |
| RF-111 | El sistema debe generar las preguntas bajo demanda sobre los tiers de pool habilitados, sin precomputar el producto cartesiano | M |
| RF-112 | El sistema debe entregar los enunciados ya compuestos, con los nombres de campeón sustituidos | M |
| RF-113 | El sistema debe acompañar cada pregunta con la definición del concepto medido, accesible a un toque | S |
| RF-114 | El sistema debe mostrar la distribución de respuestas de la comunidad tras cada respuesta, omitiéndola cuando el soporte es menor a 20 | S |

### RF-2xx — Calidad de datos

| # | Requerimiento | Pr. |
|---|---|---|
| RF-201 | El sistema debe intercalar preguntas honeypot de respuesta conocida, 1 cada 10 a 15 preguntas | M |
| RF-202 | El sistema no debe exponer nunca al cliente si una pregunta es honeypot ni su respuesta esperada | M |
| RF-203 | El sistema debe repetir una pregunta ya respondida cada ~30 preguntas para medir consistencia intra-anotador | M |
| RF-204 | El sistema debe detectar respuestas más rápidas que el umbral de lectura y rachas de *straightlining* | S |
| RF-205 | El sistema debe calcular un trust score por respondedor, derivado de honeypots, retests y patrones degenerados | M |
| RF-206 | El trust score debe usarse como peso en las agregaciones y como criterio de filtrado en la exportación | M |
| RF-207 | El sistema no debe exponer el trust score en ninguna interfaz pública | M |
| RF-208 | El sistema debe marcar a los respondedores cuya huella acumule más de 5 identidades en 24 horas | S |
| RF-209 | El sistema debe limitar la tasa a 40 respuestas por minuto y 1 500 por día, por respondedor y por hash de IP | M |

### RF-3xx — Gamificación

| # | Requerimiento | Pr. |
|---|---|---|
| RF-301 | El sistema debe llevar la racha actual y la mejor racha de cada respondedor | S |
| RF-302 | El sistema debe mostrar un perfil con cantidad de respuestas, rachas, tasa de acuerdo y cobertura por tipo | S |
| RF-303 | El sistema debe ofrecer una tabla de posiciones ordenada por cantidad de respuestas, con ventanas de día, semana y total | C |
| RF-304 | La tabla de posiciones debe usar alias generados, nunca identificadores reales, y excluir a los respondedores marcados | S |

### RF-4xx — Administración

| # | Requerimiento | Pr. |
|---|---|---|
| RF-401 | El sistema debe ofrecer un panel con volumen de respuestas, cobertura por campeón y dimensión, y distribución del trust score | S |
| RF-402 | El panel debe mostrar el estado de conectividad del grafo de comparaciones por dimensión | S |
| RF-403 | El panel debe permitir activar un parche, promover campeones de tier y disparar una corrida de agregación | S |
| RF-404 | Los endpoints de administración deben requerir una clave de acceso | M |

### RF-5xx — Agregación y exportación

| # | Requerimiento | Pr. |
|---|---|---|
| RF-501 | El sistema debe estimar scores por campeón y dimensión con Bradley-Terry ponderado por trust | M |
| RF-502 | El sistema debe estimar el minuto de pico con mediana ponderada e intervalo bootstrap | M |
| RF-503 | El sistema debe estimar los matchups con un modelo Bradley-Terry con empates y margen, por rol | M |
| RF-504 | El sistema debe estimar sinergia y fuerza de dupla tomando la dupla como competidor | S |
| RF-505 | El sistema debe estimar los atributos como proporción ponderada con intervalo de Wilson | S |
| RF-506 | Toda estimación debe acompañarse de intervalo de confianza al 95 %, soporte muestral y nivel de soporte | M |
| RF-507 | El sistema debe agregar sobre una ventana de parches con decaimiento exponencial por recencia, configurable por corrida | M |
| RF-508 | El sistema debe exportar `champion_features`, `matchup_matrix` y `duo_features` en CSV, versionados por ventana de parches | M |
| RF-509 | Cada exportación debe registrar checksum SHA-256, conteos y todos los parámetros de la corrida | M |
| RF-510 | El sistema debe distinguir en las salidas pareadas los valores observados de los predichos por el modelo | S |
| RF-511 | El sistema debe producir un Informe de Calidad de Datos con acuerdo inter-anotador, consistencia, cobertura y estabilidad por segmento | M |
| RF-512 | El sistema debe permitir reconstruir cualquier exportación previa a partir del crudo y los parámetros registrados | S |

### RF-6xx — Catálogo y versionado

| # | Requerimiento | Pr. |
|---|---|---|
| RF-601 | El sistema debe poblar el catálogo de campeones desde Data Dragon, de forma repetible por parche | M |
| RF-602 | El sistema debe versionar preguntas, respuestas y agregados por parche del juego | M |
| RF-603 | Debe ser posible agregar una dimensión o un atributo insertando una fila, sin desplegar código | S |
| RF-604 | El pool de campeones habilitados debe ser un parámetro de datos, modificable sin desplegar código | M |
| RF-605 | El sistema debe registrar el snapshot de pick rate que fundamenta el pool, con su fuente y su fecha | C |

### Fuera de esta entrega

| # | Requerimiento | Pr. |
|---|---|---|
| RF-W01 | Construcción de features por partida y consumo del dataset del laboratorio — ver [ADR-005](13-adr/ADR-005-alcance-medicion-de-campeones.md) | W |
| RF-W02 | Autenticación de usuarios o vinculación con cuentas de Riot | W |
| RF-W03 | Uso de la Riot Games API | W |
| RF-W04 | Aplicación móvil nativa | W |
| RF-W05 | Idiomas más allá de inglés y español | W |

---

## 2. Requerimientos no funcionales

| # | Requerimiento | Métrica verificable | Pr. |
|---|---|---|---|
| RNF-01 | Latencia de entrega de preguntas | `GET /questions/next` < 100 ms p95 | M |
| RNF-02 | Latencia de registro de respuestas | `POST /responses` < 150 ms p95 | M |
| RNF-03 | Peso del bundle inicial | < 200 KB gzip | S |
| RNF-04 | El crudo es inmutable | El rol de aplicación no tiene `UPDATE` ni `DELETE` sobre `responses` | M |
| RNF-05 | Privacidad | Ningún dato personal identificable en el esquema; auditable columna por columna | M |
| RNF-06 | Diseño móvil primero | Funcional y usable a 360 px de ancho, sin scroll horizontal | M |
| RNF-07 | Accesibilidad | Contraste AA, área táctil ≥ 44 px, el color nunca como único portador de información | S |
| RNF-08 | Reproducibilidad | Toda exportación reconstruible desde el crudo más los parámetros registrados | M |
| RNF-09 | Costo de infraestructura | USD 0 en niveles gratuitos, con margen documentado | S |
| RNF-10 | Cobertura de pruebas del backend | ≥ 80 % en los módulos de validación, sampler y agregación | S |
| RNF-11 | Verificación estática | `ruff`, `mypy` y `tsc --noEmit` sin errores en CI | M |
| RNF-12 | Extensibilidad | Una dimensión nueva se agrega sin modificar código ni migrar el esquema | S |

---

## 3. Trazabilidad con el Informe Inicial

Cada meta del §3.2 del Informe Inicial mapea a requerimientos concretos.

| Meta del Informe Inicial | Requerimientos |
|---|---|
| M1 — Aplicación web pública desplegada y funcional | RF-001, RF-101, RF-102, RNF-01, RNF-02, RNF-06 |
| M2 — Reemplazar el etiquetado manual por uno continuo y versionado por parche | RF-102 a RF-107, RF-501 a RF-506, RF-602 |
| M3 — Conjunto amplio de features continuas con IC | RF-506, RF-508 · **ajustada**: 20 magnitudes por campeón en vez de ~117 por partida ([ADR-005](13-adr/ADR-005-alcance-medicion-de-campeones.md)) |
| M4 — Incorporar la dimensión temporal | RF-103, RF-502 |
| M5 — Al menos 1 000 respuestas reales | RF-101, RF-114, RF-301 a RF-304 (la gamificación es el instrumento de esta meta) |
| M6 — Pipeline reproducible y trazable | RF-507, RF-509, RF-512, RNF-08 |
| M7 — Mecanismos de control de calidad | RF-201 a RF-209 |
| M8 — Informe de Calidad de Datos | RF-511 |
| M9 — Documentación técnica completa | Este repositorio; ver [`README.md`](README.md) |

**M3 es la única meta que cambió de redacción.** El Informe Inicial firmado compromete features por
partida; el alcance real entrega la medición por campeón. El ajuste se registra en el Informe de
Avance de la semana 6.
