# DraftSense

Sistema web de etiquetado *crowdsourced* para la caracterización estadística de campeones de
*League of Legends*.

Jugadores responden preguntas cortas sobre campeones. Las respuestas se agregan con métodos
estadísticos establecidos (Bradley-Terry, medianas ponderadas con IC bootstrap, proporciones con
intervalo de Wilson) y producen una medición continua por campeón, versionada por parche y con
intervalos de confianza reportables.

Reemplaza el etiquetado manual de 7 tags binarios asignados por un único anotador que hoy usa la
línea de investigación del **Laboratorio DHARMa** (UTN FRM) para su modelo de predicción de
resultados de partidas.

Desarrollado como Práctica Profesional Supervisada — Telo, Matías Ignacio, legajo 50180.
Ingeniería en Sistemas de Información, UTN Facultad Regional Mendoza. 01/09/2026 – 19/11/2026.

## Qué entrega y qué no

**Entrega:** el sistema desplegado, la recolección piloto y tres archivos de datos por parche —
`champion_features`, `matchup_matrix` y `duo_features` — más un Informe de Calidad de Datos.

**No entrega:** análisis de partidas, features por partida, integración con el modelo predictivo
ni interpretación de resultados. DraftSense mide campeones; el laboratorio hace el resto.

## Estructura

| Carpeta | Contenido |
|---|---|
| `frontend/` | SPA en React 18 + TypeScript + Vite. Interfaz pública de etiquetado |
| `backend/` | API REST en FastAPI + SQLAlchemy 2.0 async. Sesiones, sampler, registro de respuestas |
| `aggregation/` | Paquete Python ejecutable como CLI. Agregación estadística y exportación |
| `infra/` | Migraciones Alembic, seeds, configuración de despliegue |
| `docs/` | Documentación técnica — **empezar por [`docs/README.md`](docs/README.md)** |

## Puesta en marcha local

Requisitos: **Python 3.12 o superior**, **Node 20 o superior** y un **PostgreSQL 16** accesible.

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate en Linux/macOS
pip install -e ".[dev]"

# Apuntar a la base
export DS_DATABASE_URL="postgresql+asyncpg://draftsense:draftsense@localhost:5432/draftsense"

alembic upgrade head            # crea el esquema
python -m app.cli seed-catalog  # 8 dimensiones y 7 atributos
python -m app.cli seed-champions --patch 16.20
```

### Frontend

```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173, con proxy de /api al backend
```

### Comprobaciones

```bash
cd backend && ruff check . && mypy app && pytest -q
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
python infra/check_docs.py      # DDL, enlaces y conteos de la documentación
```

Los tests del backend corren **sin base de datos**: los que la requieren se saltean solos y se
ejecutan en CI, que levanta un Postgres 16 real.

### Operación

```bash
python -m app.cli check-seeds                       # valida los YAML sin tocar la base
python -m app.cli seed-champions --patch 16.20      # relee Data Dragon
python -m app.cli fetch-ddragon --out ../infra/seeds/ddragon_champions_snapshot.json
```

El snapshot de Data Dragon versionado en `infra/seeds/` es el respaldo que usa el seeder cuando el
CDN de Riot no responde.

## Aviso legal

DraftSense no está afiliado, respaldado ni patrocinado por Riot Games. *League of Legends* y sus
activos son propiedad de Riot Games, Inc. Las imágenes de campeones se obtienen de Data Dragon,
el CDN público de Riot. Ver [`docs/33-privacidad-y-legal.md`](docs/33-privacidad-y-legal.md).
