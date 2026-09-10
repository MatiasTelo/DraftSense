# Mapa de la documentación — qué pregunta responde qué documento

Todo lo de acá vive en `draftsense/docs/`. Las rutas son relativas a esa carpeta.
Esta tabla no resume los documentos: dice **dónde mirar**. El contenido se lee del original.

## Por pregunta

| Si necesitás saber... | Andá a |
|---|---|
| Qué requerimiento numerado cubre una funcionalidad (RF/RNF) | `01-requerimientos.md` §1 y §2 |
| Cómo se traza un requerimiento contra el Informe Inicial | `01-requerimientos.md` §3 |
| El flujo de un actor punta a punta (CU-01 … CU-10) | `02-casos-de-uso.md` |
| El criterio Dado/Cuando/Entonces de una funcionalidad | `03-criterios-aceptacion.md` (§1 sesión, §2 preguntas, §3 respuestas, §4 calidad, §5 agregación, §6 interfaz, §7 operación, §8 gamificación) |
| Qué componentes hay y cómo se despliegan | `10-arquitectura.md` §1 y §2 |
| Qué pasa exactamente cuando alguien responde una pregunta | `10-arquitectura.md` §3 |
| Los jobs de fondo y qué pasa cuando algo falla | `10-arquitectura.md` §4 y §7 |
| El DDL de una tabla, sus índices o sus constraints | `11-modelo-de-datos.md` §3 |
| Cómo se garantiza el append-only de `responses` | `11-modelo-de-datos.md` §4 |
| El esquema JSON que valida un `answer` | `11-modelo-de-datos.md` §5 |
| El contrato de un endpoint, sus errores o su rate limit | `12-api.md` §2, §3, §4 |
| Los principios del contrato REST (quién arma los textos, unión por `type`) | `12-api.md` §1 |
| Por qué una decisión de diseño es la que es | `13-adr/` — ver `invariantes.md` |
| El enunciado, la UI, el payload y los casos borde de un tipo de pregunta | `20-tipos-de-pregunta.md` §2 a §6 (uno por tipo) |
| En qué orden se implementan los 5 tipos | `20-tipos-de-pregunta.md` §8 |
| Cómo elige el sampler la próxima pregunta | `21-sampler.md` §3 (prioridad) y §4 (regímenes y exploración) |
| Cómo se generan las preguntas sin enumerarlas todas | `21-sampler.md` §2 |
| El pseudocódigo completo del sampler | `21-sampler.md` §10 |
| Qué es una honeypot y de dónde sale el catálogo | `22-calidad-de-datos.md` §3 |
| Cómo se detecta un patrón degenerado o un duplicado | `22-calidad-de-datos.md` §5 y §6 |
| La fórmula del trust score y cuándo se recalcula | `22-calidad-de-datos.md` §7 |
| Cómo funcionan las rachas, el perfil o la tabla de posiciones | `23-gamificacion.md` §2, §3, §5 |
| El panel de administración | `24-panel-admin.md` — **pendiente** |
| Qué respuestas entran a una corrida y cuáles no | `25-agregacion.md` §1 |
| Cómo se pondera una respuesta | `25-agregacion.md` §2 |
| Para qué sirven el rol, el tiempo de juego y el rango declarados | `25-agregacion.md` §3 |
| Cómo se calcula un intervalo de confianza, `_n` o `_support` | `25-agregacion.md` §4 |
| El estimador de un tipo de pregunta concreto | `25-agregacion.md` §5 |
| Cómo se corre una exportación y con qué parámetros | `25-agregacion.md` §8 y §9 |
| Qué significa una columna del CSV, su rango y su origen | `26-esquema-de-salida.md` §3, §4, §5 |
| Las convenciones de nombres y valores faltantes del CSV | `26-esquema-de-salida.md` §2 |
| Cómo consume el laboratorio los archivos | `26-esquema-de-salida.md` §6 |
| Krippendorff, test-retest, cobertura, Informe de Calidad de Datos | `27-validacion-confiabilidad.md` — **pendiente** |
| El wireframe, los estados o el microcopy de una pantalla | `30-ux-flujos.md` §3 a §7 (una por ruta) |
| Decisiones de interfaz ya cerradas | `30-ux-flujos.md` §10 |
| Un ejemplo ejecutable de los tres CSV, columna por columna | `examples/README.md` |

## Estado de cada documento

Los estados son los que declara `docs/README.md`. **Si cambian ahí, cambian acá.**

| Documento | Estado |
|---|---|
| `01-requerimientos.md` | v1 |
| `02-casos-de-uso.md` | v1 |
| `03-criterios-aceptacion.md` | v1 |
| `10-arquitectura.md` | v1 |
| `11-modelo-de-datos.md` | v1 |
| `12-api.md` | v1 |
| `13-adr/` (16 ADR) | v1 |
| `20-tipos-de-pregunta.md` | v1 |
| `21-sampler.md` | v1 |
| `22-calidad-de-datos.md` | v1 |
| `23-gamificacion.md` | v1 |
| `24-panel-admin.md` | **pendiente** |
| `25-agregacion.md` | v1 |
| `26-esquema-de-salida.md` | v1 |
| `examples/` | v1 |
| `27-validacion-confiabilidad.md` | **pendiente** — desbloquea la semana 10 |
| `30-ux-flujos.md` | v1 |
| `31-plan-de-pruebas.md` | **pendiente** |
| `32-despliegue.md` | **pendiente** |
| `33-privacidad-y-legal.md` | **pendiente** |
| `34-plan-piloto.md` | **pendiente** |
| `35-glosario.md` | **pendiente** |

Un documento `pendiente` es un stub: declara qué va a contener y qué semana desbloquea, nada más.
**No implementes la funcionalidad que describe sin escribirlo primero.**

## Fuera del repo

En la carpeta de la PPS, un nivel arriba:

| Archivo | Qué es | Cuidado |
|---|---|---|
| `docs/md files/DraftSense_Especificacion_Tecnica.md` | Documento paraguas, v1.0 de agosto 2026 | **Registro histórico, no especificación vigente.** Lleva nota de erratas (08/09/2026): lo que dice sobre `match_features.csv` y las 117 features por partida está sin efecto. La organización ya está corregida |
| `docs/md files/Informe_Inicial_PPS_Telo_v2.md` | El Informe Inicial firmado | Mismo desvío de alcance. **No se toca**: está firmado |
| `docs/Entregas/` | Los .docx y .pdf ya entregados | Sólo lectura |
