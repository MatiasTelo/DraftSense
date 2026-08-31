# ADR-007 — Backend en FastAPI sobre Python

> Estado: **aceptada** · Fecha: 31/08/2026

## Contexto

El sistema tiene dos mitades que comparten el mismo modelo de datos: la API que recolecta respuestas
y el pipeline que las agrega estadísticamente. El pipeline es **inevitablemente Python**: `choix`
para Bradley-Terry, `scipy` para el bootstrap, `krippendorff` para el acuerdo inter-anotador,
`pandas` para los CSV. No existen equivalentes maduros en otros ecosistemas.

Además, el laboratorio que recibe el sistema trabaja en Python.

## Decisión

Backend en **FastAPI 0.115+ sobre Python 3.12**, con SQLAlchemy 2.0 en modo asincrónico
(`asyncpg`), Pydantic v2 para los esquemas y Alembic para las migraciones.

## Alternativas consideradas

- **Node/Express o NestJS.** Obligaría a mantener dos runtimes, dos toolchains de CI y **dos
  definiciones del modelo de datos** —una en TypeScript para la API, otra en Python para la
  agregación— que se desincronizarían en la primera semana de cambios. El costo de esa duplicación
  supera cualquier ventaja.
- **Django + DRF.** Batteries included y un admin gratis, pero el ORM síncrono y un peso conceptual
  grande para una API de siete endpoints. El panel de administración de este sistema muestra
  métricas agregadas, que no es lo que el admin de Django resuelve bien.
- **Flask.** Más liviano, pero sin validación por tipos ni OpenAPI autogenerada, que son justamente
  lo que hace que el contrato con el frontend TypeScript no se desincronice.

## Consecuencias

- Los modelos SQLAlchemy se **comparten** entre la API y el pipeline de agregación: una sola
  definición del esquema para todo el sistema.
- La documentación OpenAPI se genera sola y es la fuente del contrato para el frontend.
- El laboratorio puede leer, correr y extender el pipeline sin aprender un stack nuevo, que es una
  condición de la transferencia de la semana 12.
- El frontend queda en TypeScript, con la frontera de lenguajes exactamente en la API REST, donde
  el contrato está tipado de los dos lados.
