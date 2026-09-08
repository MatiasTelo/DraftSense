# DraftSense

Sistema web de etiquetado *crowdsourced* para la caracterización estadística de campeones de
League of Legends. Práctica Profesional Supervisada — Laboratorio DHARMa, UTN FRM.

## Alcance — leer antes que nada

**DraftSense mide campeones.** No analiza partidas, no construye features por partida, no consume
el dataset de partidas del laboratorio, no se integra con el modelo predictivo y no interpreta
resultados. La frontera de la práctica es el CSV.

La salida son tres archivos —`champion_features`, `matchup_matrix`, `duo_features`— más el Informe
de Calidad de Datos. La métrica de impacto es **20 magnitudes continuas por campeón, con intervalo
de confianza y soporte muestral, versionadas por parche (126 columnas), frente a 7 etiquetas
binarias de un anotador único**.

Esto está fijado en [`docs/13-adr/ADR-005-alcance-medicion-de-campeones.md`](docs/13-adr/ADR-005-alcance-medicion-de-campeones.md)
y **difiere del Informe Inicial firmado**, que promete un `match_features.csv` con ~117 features
por partida. No re-derives el alcance a partir de él. La Especificación Técnica decía lo mismo y
desde el 08/09/2026 lleva una nota de erratas que lo declara sin efecto. El desvío debe registrarse
en el Informe de Avance de la semana 6; el informe firmado no se toca.

## Orden de trabajo

La documentación de `docs/` se escribe **antes** que el código de esa semana, no después.

Un documento en estado `v1` es contrato. Cambiarlo exige anotar el cambio y, si contradice una
decisión ya tomada, un ADR nuevo que la reemplace. Los estados son
`pendiente` → `borrador` → `v1` → `vN`.

Toda decisión de diseño no obvia se registra como ADR en `docs/13-adr/`. Un documento de
especificación describe *qué* y *cómo*; el ADR explica *por qué* y qué se descartó.

## Verificación

```bash
cd backend && ruff check . && mypy app && pytest -q
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
python infra/check_docs.py
```

Es exactamente lo que corre `.github/workflows/ci.yml`. `check_docs.py` valida el DDL con sqlglot,
los enlaces internos entre documentos y los conteos de columnas de `26-esquema-de-salida.md`.

Los tests del backend que necesitan base se saltean solos si no hay `DS_DATABASE_URL`. Corren los
diez con un `backend/.env` configurado, y siempre en CI contra un Postgres 17 real.

## Estructura

| Carpeta | Contenido |
|---|---|
| `frontend/` | SPA React 18 + TypeScript + Vite |
| `backend/` | API REST FastAPI + SQLAlchemy 2.0 async |
| `aggregation/` | Paquete Python ejecutable como CLI. **Vacío hasta la semana 9** |
| `infra/` | Seeds, `check_docs.py`, configuración de despliegue |
| `docs/` | Documentación técnica — empezar por [`docs/README.md`](docs/README.md) |

## Convenciones

- **Idioma:** documentación y comentarios en español; código, identificadores y textos de la
  interfaz pública en inglés ([ADR-010](docs/13-adr/ADR-010-interfaz-en-ingles.md)).
- Los comentarios explican **por qué**, no qué. Si el código no es obvio, el comentario dice qué
  se rompe si se cambia.
- Requisitos: Python 3.12+, Node 20+, PostgreSQL 15+ (el esquema usa `NULLS NOT DISTINCT`).

## Qué nunca versionar

`.env`, los CSV de salida y `exports/` ya están en `.gitignore`. Además: **ninguna credencial
dentro de `.claude/`**, que sí se versiona y viaja al repo público.

## Mantener las skills sincronizadas

Las skills de `.claude/skills/` rutean a `docs/` en vez de copiarla: nunca son la fuente de verdad
de algo que ya está documentado. Si tocaste `docs/**`, un ADR o este README, revisá la skill
afectada antes de cerrar. Al terminar una semana del cronograma, actualizá
`.claude/skills/draftsense/references/cronograma.md`.

## Ante la duda, preguntar

Si el alcance de una tarea es ambiguo, si un dato no está en ningún documento, o si dos documentos
se contradicen: preguntá antes de avanzar. No inventes valores, nombres, fórmulas ni requisitos.
