# Documentación técnica de DraftSense

Esta carpeta contiene la especificación completa del sistema: qué hace cada funcionalidad, cómo
está construida y por qué se decidió así. Los documentos se escriben **antes** que el código de
cada semana del cronograma, no después.

El documento paraguas es `DraftSense_Especificacion_Tecnica.md` (fuera de este repo, en la carpeta
de la PPS). Fija el marco general; acá está el detalle ejecutable.

## Índice

### Especificación funcional — qué hace el sistema
| Doc | Contenido | Estado |
|---|---|---|
| [`01-requerimientos.md`](01-requerimientos.md) | RF/RNF numerados con prioridad, trazables a los objetivos del Informe Inicial | **v1** |
| [`02-casos-de-uso.md`](02-casos-de-uso.md) | Actores y flujos principal / alternativo / excepciones | **v1** |
| [`03-criterios-aceptacion.md`](03-criterios-aceptacion.md) | Dado/Cuando/Entonces por funcionalidad; guion de los tests E2E | **v1** |

### Diseño técnico — cómo está construido
| Doc | Contenido | Estado |
|---|---|---|
| [`10-arquitectura.md`](10-arquitectura.md) | Componentes, despliegue, recorrido de una respuesta punta a punta | **v1** |
| [`11-modelo-de-datos.md`](11-modelo-de-datos.md) | DDL completo, diccionario de datos, esquemas JSON, migraciones | **v1** |
| [`12-api.md`](12-api.md) | Contrato REST completo: endpoints, errores, cookies, rate limit | **v1** |
| [`13-adr/`](13-adr/) | Registro de decisiones de arquitectura | **v1** |

### Especificación por funcionalidad — el detalle de cada característica
| Doc | Contenido | Estado |
|---|---|---|
| [`20-tipos-de-pregunta.md`](20-tipos-de-pregunta.md) | Los 5 tipos: enunciado, UI, payload, validación, generación, casos borde | **v1** |
| [`21-sampler.md`](21-sampler.md) | Sampling adaptativo: prioridad, exploración, composición de sesión, arranque en frío | **v1** |
| [`22-calidad-de-datos.md`](22-calidad-de-datos.md) | Honeypots, test-retest, patrones degenerados, trust score, deduplicación | **v1** |
| [`23-gamificacion.md`](23-gamificacion.md) | Rachas, acuerdo con el consenso, perfil, leaderboard, anti-gaming | **v1** |
| [`24-panel-admin.md`](24-panel-admin.md) | Métricas, vistas, acciones de operación, autenticación | pendiente |
| [`25-agregacion.md`](25-agregacion.md) | Del respondedor al CSV: qué se hace con los datos declarados, ponderación, los 5 estimadores y los casos límite | **v1** |
| [`26-esquema-de-salida.md`](26-esquema-de-salida.md) | Los tres CSV columna por columna: fórmula, rango, origen, soporte | **v1** |
| [`examples/`](examples/) | Ejemplo ejecutable de los tres CSV, con el diccionario de cada columna | **v1** |
| [`27-validacion-confiabilidad.md`](27-validacion-confiabilidad.md) | Krippendorff, test-retest, cobertura, estabilidad por segmento | pendiente |

### Producto y operación
| Doc | Contenido | Estado |
|---|---|---|
| [`30-ux-flujos.md`](30-ux-flujos.md) | Navegación, wireframes, estados por pantalla, microcopy | **v1** |
| [`31-plan-de-pruebas.md`](31-plan-de-pruebas.md) | Niveles, casos críticos, datos de prueba | pendiente |
| [`32-despliegue.md`](32-despliegue.md) | Entornos, variables, secretos, CI/CD, runbook | pendiente |
| [`33-privacidad-y-legal.md`](33-privacidad-y-legal.md) | Qué se guarda y qué no, política de privacidad, aviso de Riot | pendiente |
| [`34-plan-piloto.md`](34-plan-piloto.md) | Canales, oleadas, métricas de éxito, plan B | pendiente |
| [`35-glosario.md`](35-glosario.md) | Términos de LoL y de estadística | pendiente |

## Convenciones

- **Idioma:** la documentación se escribe en español; el código, los identificadores y la interfaz
  pública, en inglés. Los textos visibles al usuario van en inglés primero (ver [ADR-010](13-adr/ADR-010-interfaz-en-ingles.md)).
- **Decisiones:** toda decisión de diseño no obvia se registra como ADR en `13-adr/`. Un documento
  de especificación describe *qué* y *cómo*; el ADR explica *por qué* y qué se descartó.
- **Estado:** `pendiente` → `borrador` → `v1` → `vN`. Un documento en `v1` es contrato: cambiarlo
  requiere anotar el cambio y, si contradice una decisión, un ADR que la reemplace.

## Alcance — leer antes que nada

DraftSense **mide campeones**. No analiza partidas, no construye features por partida, no consume
el dataset de partidas del laboratorio. La salida son tres tablas a nivel de campeón o de par de
campeones, más el Informe de Calidad de Datos.

Esto **difiere del Informe Inicial firmado**, que compromete además un `match_features.csv` con
~117 features por partida. El ajuste está justificado en [ADR-005](13-adr/ADR-005-alcance-medicion-de-campeones.md)
y debe quedar registrado en el Informe de Avance de la semana 6.
