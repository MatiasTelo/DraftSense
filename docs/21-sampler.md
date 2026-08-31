# 21 — Sampling adaptativo

> Estado: **pendiente** · Ola 3 · Desbloquea la semana 5 del cronograma

Este documento todavía no está escrito. Se redacta antes de implementar la funcionalidad que
describe, no después.

## Contenido previsto

- Función de prioridad con sus cuatro términos y pesos.
- Exploración ε-greedy y composición de la sesión (mezcla de tipos, honeypots, retests).
- Régimen de arranque en frío (ADR-012) y transición al régimen normal.
- Chequeo de componentes conexas y prioridad de aristas puente (ADR-008).
- Generación perezosa de preguntas sobre el pool habilitado.

## Decisiones abiertas a resolver al escribirlo

- Valor de ε.
- Criterio numérico para promover un campeón al siguiente `pool_tier` durante el piloto.
- Frecuencia real de los jobs de recálculo, a validar contra el costo observado.

---

Ver el índice en [`README.md`](README.md) y las decisiones ya cerradas en [`13-adr/`](13-adr/).
