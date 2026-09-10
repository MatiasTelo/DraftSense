# Cronograma y estado real

> **Última actualización de este archivo: 09/09/2026.** Es el archivo de la skill que más se
> desactualiza. Al cerrar una semana, actualizar la columna Estado y la fecha de arriba.

Período 01/09/2026 – 19/11/2026, L–V 8:00–12:00. 200 hs planificadas sobre 228 hs de disponibilidad
efectiva (58 días hábiles menos el feriado del 12/10), o sea 28 hs de margen. La semana 6 tiene 16 hs
por ese feriado y la semana 12 tiene 8 hs por comprender sólo tres días hábiles.

## Las 12 semanas

| Sem. | Período | Entregable | Hs | Estado |
|---|---|---|---|---|
| 1 | 01/09 – 07/09 | Esquema de base de datos versionado y entorno de staging operativo | 20 | **cerrada** |
| 2 | 08/09 – 14/09 | API REST núcleo funcional con pruebas automatizadas | 20 | **cerrada** |
| 3 | 15/09 – 21/09 | Primer tipo de pregunta operativo de extremo a extremo | 20 | **en curso** |
| 4 | 22/09 – 28/09 | Tipos de pregunta 2 y 3 operativos con feedback | 20 | pendiente |
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

## Estado real del repositorio

Al 09/09/2026:

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
- **`aggregation/` está vacía.** El paquete se implementa en la semana 9.
- **Lo que NO tiene el backend todavía:** el sampler completo (semana 5 — hoy `/questions/next`
  sortea uniforme sobre el tipo 1), honeypots, retests y trust score (semana 5), los `/admin/*`
  (semana 7) y los cuatro jobs de fondo.
- **`frontend/src/` sigue siendo andamiaje**: `App.tsx` es sólo el landing y `api.ts` tiene los
  tipos del contrato, ya alineados con `12-api.md`. Las pantallas son de la semana 3 en adelante.

## Entregables académicos

| Cuándo | Qué |
|---|---|
| Semana 6 (06/10 – 12/10) | **Informe de Avance** + informes de los dos tutores |
| Semana 12 (17/11 – 19/11) | **Informe Final** + informes de los dos tutores + transferencia |

Los redacta la skill `pps-informes`, que vive en `.claude/skills/` de la carpeta de la PPS (fuera de
este repo, porque los informes también están fuera).
