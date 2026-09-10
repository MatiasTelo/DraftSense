# Invariantes — lo que ya está decidido

Todo lo de acá está cerrado. No se replantea como si fuera una opción abierta; si hay que cambiarlo,
se escribe un ADR nuevo que reemplace al viejo. Las rutas son relativas a `draftsense/docs/`.

## Las 16 decisiones de arquitectura

Cada línea es la decisión, no el razonamiento. El *por qué* y las alternativas descartadas están en
el ADR; leerlo entero antes de contradecirlo.

| ADR | Decisión |
|---|---|
| **001** sin autenticación | No hay registro ni login. La identidad es una sesión anónima en cookie `ds_session` (`HttpOnly`, `Secure`, `SameSite=Lax`, 180 días). En base se guarda **sólo el SHA-256** del token. No se almacena email, nombre, IP en claro ni cuenta de Riot |
| **002** responses append-only | Una respuesta **nunca** se modifica ni se borra. Las correcciones de calidad son *pesos* en la agregación y *filtros parametrizados* en el export. Se garantiza con permisos de Postgres: al rol `draftsense_app` se le revoca `UPDATE`, `DELETE` y `TRUNCATE` |
| **003** Bradley-Terry | Comparaciones pareadas ajustadas con Bradley-Terry por dimensión, ponderado por trust, vía `choix.ilsr_pairwise`. IC por bootstrap (2 000 remuestreos). El tipo 3 usa la generalización de **Rao-Kupper**, que admite empates y margen |
| **004** ventana de parches con decaimiento | El crudo se versiona por parche siempre (`responses.patch_id` nunca se pierde). La agregación corre sobre una **ventana** de parches, ponderando por recencia con decaimiento exponencial de vida media configurable |
| **005** alcance | **DraftSense mide campeones y entrega esa medición.** No consume el dataset de partidas, no construye features por partida, no se integra con el modelo, no interpreta resultados. Salida: tres archivos + Informe de Calidad de Datos |
| **006** pool escalonado | `champions.pool_tier` define 3 niveles: 1 núcleo, 2 expansión, 3 el resto (tamaños reales en ADR-016: 58 y 96). El sampler sólo usa los habilitados. **Promover un campeón es un `UPDATE`, no un despliegue.** El núcleo sale de un snapshot manual de pick rate versionado en `infra/seeds/` |
| **007** FastAPI | Backend FastAPI 0.115+ sobre Python 3.12, SQLAlchemy 2.0 async (`asyncpg`), Pydantic v2, Alembic |
| **008** conectividad por componentes | Un job horario `check_graph_connectivity` calcula las componentes conexas del grafo de comparaciones por dimensión y marca `bridge_priority = true` en las preguntas que las unirían; el sampler las pone por encima de escasez y entropía. **No se designan campeones ancla** |
| **009** curva de poder gaussiana | `power_at(t) = exp(-(t - peak_minute)² / (2·σ²))`, con `σ` global calibrado en el piloto y registrado en `exports` |
| **010** interfaz en inglés | La interfaz pública se construye en inglés desde el día 1; el español entra por i18n hacia la semana 8. Documentación e informes en español; código, identificadores y textos de interfaz en inglés. `dimensions` y `traits` tienen `label_en` obligatorio y `label_es` nulable |
| **011** support_level en vez de excluir | **Se exporta todo.** Cada magnitud lleva valor, IC 95 %, `_n` y `_support` (`solid` / `limited` / `insufficient`). Una magnitud sin datos se escribe **celda vacía, nunca `0`**, con `_n = 0` y `_support = insufficient` |
| **012** sampler uniforme en arranque en frío | Con menos de **5 respuestas** una pregunta se sortea uniforme, sin función de prioridad; desde la quinta entra la prioridad completa. El feedback de consenso se omite con menos de **20 respuestas** y la interfaz muestra *"you're one of the first to answer this"* |
| **013** honeypots verificables desde el kit | Cada honeypot sale de un hecho verificable del kit del campeón, escrito en un campo `rationale` obligatorio del seed. Sólo **6 de las 8 dimensiones** admiten honeypots: `mobility`, `cc`, `poke`, `waveclear`, `engage`, `peel`. **`scaling` y `pick` no tienen ninguna** |
| **014** leaderboard filtra por confianza | La tabla excluye a los `is_flagged` y a los que están debajo de `export.min_trust` (0.30), usando **literalmente la misma clave de `app_settings`** que el filtro de exportación, no una copia |
| **015** estructura en capas | Backend en cuatro capas con dependencia en un solo sentido: `routers → services → models`, y `schemas` transversal. **Un service no importa nada de `fastapi`.** Todo error sale por `ApiError` con el sobre de `12-api.md` §3; el rate limit se cuenta sobre `responses_by_respondent`, sin Redis |
| **016** carga inicial del pool | La primera carga del snapshot aplica los cortes de `21-sampler.md` §7.1: top 12 de algún rol → tier 1, top 20 → tier 2, el resto tier 3. Sobre el snapshot de 16.17 da **58 y 96**, no los «~40» y «~80» que estimaba ADR-006, que quedan sin efecto |

## Los cinco tipos de pregunta

En firme desde el 21/08/2026, **no son opcionales**. Detalle en `20-tipos-de-pregunta.md`, contrato
en `12-api.md` §2.3, estimador de cada uno en `25-agregacion.md` §5.

| # | Tipo | `type` de la API | Alimenta |
|---|---|---|---|
| 1 | Comparación pareada por dimensión | `pairwise_dimension` | Las 8 dimensiones funcionales |
| 2 | Slider de pico de poder | `peak_timing` | `peak_minute` y la curva de poder |
| 3 | Enfrentamiento de línea (1v1 y 2v2) | `lane_matchup` | Fuerza de línea, `matchup_matrix`, `duo_features.lane_strength` |
| 4 | Sinergia de dupla | `duo_synergy` | `synergy` y `synergy_mean` |
| 5 | Multi-selección de atributos | `trait_multiselect` | Los 7 atributos |

## La salida

Tres CSV por parche más el Informe de Calidad de Datos. Contrato completo en
`26-esquema-de-salida.md`; los conteos de columnas los **verifica `infra/check_docs.py` en CI**.

| Archivo | Grano | Columnas |
|---|---|---|
| `champion_features_v<patch>.csv` | un campeón | 126 (7 identificación + 56 dimensiones + 10 pico + 15 línea + 3 sinergia + 35 atributos) |
| `matchup_matrix_v<patch>.csv` | campeón_a × campeón_b × rol | 12 |
| `duo_features_v<patch>.csv` | una dupla | 18 |

20 magnitudes medidas por campeón: 8 dimensiones + 1 pico + 3 líneas + 1 sinergia + 7 atributos.

## Contradicciones vivas del proyecto

Hay que conocerlas para no "corregir" un documento hacia el lado equivocado.

1. **Alcance.** ADR-005 (31/08/2026) recortó el alcance. El **Informe Inicial firmado por ambos
   tutores** y la **`DraftSense_Especificacion_Tecnica.md`** todavía comprometen `match_features.csv`
   y ~117 features por partida. El repo está bien; esos dos documentos están desactualizados.
   - El informe firmado **no se toca**.
   - El desvío **debe registrarse y justificarse en el Informe de Avance de la semana 6**.
   - La Especificación Técnica **lleva una nota de erratas desde el 08/09/2026** que declara sin
     efecto todo lo que dice sobre features por partida y remite al repositorio. El cuerpo del
     documento se dejó como registro histórico: no lo cites como especificación vigente.
2. **Organización.** Es el **Laboratorio DHARMa**, y el equipo dueño de la línea de investigación se
   nombra como "el laboratorio". Ya no queda ninguna mención a la "Cátedra de Ciencia de Datos" en
   los documentos de entrega ni en la Especificación Técnica.
3. **Tailwind.** La Especificación Técnica lo fija como sistema de estilos, pero
   `frontend/package.json` no lo tiene instalado. Sin resolver — preguntar antes de introducirlo.

## Datos formales de la PPS

De la Resolución (Anexo I). **No se re-derivan ni se cambian.**

- Alumno: Telo, Matías Ignacio · Legajo 50180
- Organización: Laboratorio DHARMa, lab de I+D del Depto. de Ing. en Sistemas, UTN FRM, Mendoza
- Tutor de la Organización: **Pablo Marinozi**, Co-director del Laboratorio DHARMa
- Tutor de la Universidad: **Mario Centeno**, Cátedra Seguridad en Sistemas de Información
- Período: 01/09/2026 – 19/11/2026, L–V 8:00–12:00, 200 hs, 12 semanas

El detalle de formato de los informes está en la skill `pps-informes`, en la carpeta de la PPS.
