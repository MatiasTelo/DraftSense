# 22 — Calidad de datos y trust score

> Estado: **pendiente** · Ola 3 · Desbloquea la semana 5 del cronograma

Este documento todavía no está escrito. Se redacta antes de implementar la funcionalidad que
describe, no después.

## Contenido previsto

- Honeypots: criterios de selección, catálogo por parche, proceso de validación con el tutor.
- Test-retest: cadencia, selección de la pregunta a repetir, medición de consistencia.
- Detección de patrones degenerados: respuestas apuradas, straightlining, sesiones anómalas.
- Fórmula del trust score, momento de recálculo y uso dual (peso y filtro).
- Deduplicación por fingerprint y política de marcado.

## Decisiones abiertas a resolver al escribirlo

- Quién redacta el catálogo de honeypots (~40 pares por parche) y en qué semana.
- Umbral de trust para el filtro del export: 0.30 es la primera estimación, se calibra con datos reales.

---

Ver el índice en [`README.md`](README.md) y las decisiones ya cerradas en [`13-adr/`](13-adr/).
