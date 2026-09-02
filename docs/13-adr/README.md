# Registro de decisiones de arquitectura (ADR)

Cada ADR documenta **una** decisión: el contexto que la forzó, lo que se decidió, qué alternativas
se descartaron y con qué consecuencias hay que vivir.

Un documento de especificación describe *qué* y *cómo*. El ADR explica *por qué*, y sobre todo qué
se consideró y se dejó de lado — que es lo que no se puede reconstruir leyendo el código.

Los ADR **no se editan cuando cambia la decisión**: se marcan como `sustituida por ADR-NNN` y se
escribe uno nuevo. El registro es histórico.

| # | Decisión | Estado |
|---|---|---|
| [001](ADR-001-sin-autenticacion.md) | Sin autenticación: sesión anónima por cookie | aceptada |
| [002](ADR-002-responses-append-only.md) | `responses` es append-only | aceptada |
| [003](ADR-003-bradley-terry.md) | Bradley-Terry para los scores de dimensión | aceptada |
| [004](ADR-004-ventana-de-parches-con-decaimiento.md) | Versionado por parche en el crudo, ventana con decaimiento en la agregación | aceptada |
| [005](ADR-005-alcance-medicion-de-campeones.md) | El alcance es la medición de campeones, no el análisis de partidas | aceptada |
| [006](ADR-006-pool-escalonado-por-pick-rate.md) | Pool escalonado, definido por un snapshot de pick rate | aceptada |
| [007](ADR-007-fastapi-python.md) | Backend en FastAPI sobre Python | aceptada |
| [008](ADR-008-conectividad-por-componentes.md) | Conectividad del grafo por chequeo de componentes, sin anclas | aceptada |
| [009](ADR-009-curva-de-poder-gaussiana.md) | Curva de poder gaussiana a nivel campeón | aceptada |
| [010](ADR-010-interfaz-en-ingles.md) | Interfaz en inglés primero, español después | aceptada |
| [011](ADR-011-support-level-en-vez-de-excluir.md) | Exportar todo con `support_level`, no excluir bajo umbral | aceptada |
| [012](ADR-012-sampler-uniforme-en-arranque-en-frio.md) | Sampler uniforme durante el arranque en frío | aceptada |
| [013](ADR-013-honeypots-verificables-desde-el-kit.md) | Las honeypots se derivan del kit del campeón, no del juicio experto | aceptada |
| [014](ADR-014-leaderboard-filtra-por-confianza.md) | La tabla de posiciones filtra por confianza, sin exponerla | aceptada |

## Cuál merece un ADR

Uno que cierre una discusión real: si alguien razonable podría haber elegido distinto, va ADR.
Las decisiones obvias o forzadas por el entorno no lo necesitan.

**ADR-005 es el que hay que leer primero.** Es el único que se aparta de lo comprometido en el
Informe Inicial firmado, y debe registrarse en el Informe de Avance de la semana 6.
