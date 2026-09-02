# 24 — Panel de administración

> Estado: **pendiente** · Ola 3 · Desbloquea la semana 7 del cronograma

Este documento todavía no está escrito. Se redacta antes de implementar la funcionalidad que
describe, no después.

## Contenido previsto

- Métricas de volumen, cobertura por campeón y dimensión, distribución del trust score.
- Estado de conectividad del grafo por dimensión.
- Los dos indicadores que deciden habilitar el tier siguiente ([`21-sampler.md`](21-sampler.md) §7.2).
- Vistas y maquetado de cada pantalla.

**El contrato de las acciones ya está cerrado** y no hay que volver a decidirlo al escribir este
documento: los cinco endpoints están en [`12-api.md`](12-api.md) §2.7 —activar parche, promover tier,
cambiar un parámetro, marcar un respondedor y disparar una corrida—, la autenticación es
`X-Admin-Key`, y las tablas `app_settings` y `admin_audit` están en
[`11-modelo-de-datos.md`](11-modelo-de-datos.md) §3.12 y §3.13. Lo que falta acá es la **interfaz**:
qué se ve, cómo se agrupa y en qué orden.

---

Ver el índice en [`README.md`](README.md) y las decisiones ya cerradas en [`13-adr/`](13-adr/).
