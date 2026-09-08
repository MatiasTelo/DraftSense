---
name: draftsense
description: >-
  Contexto maestro del proyecto DraftSense — sistema web de etiquetado crowdsourced de campeones de
  League of Legends, Práctica Profesional Supervisada en el Laboratorio DHARMa (UTN FRM). Usar
  SIEMPRE al trabajar sobre cualquier parte de DraftSense: antes de escribir código, de redactar o
  modificar documentación de `docs/`, de crear un ADR, de estimar una semana del cronograma o de
  responder qué hace o qué no hace el sistema. Activar también ante preguntas de alcance ("¿esto
  entra en la PPS?", "¿DraftSense analiza partidas?", "¿qué exporta?"), ante cualquier mención de
  match_features, features por partida, champion_features, matchup_matrix, duo_features,
  trust score, honeypots, sampler, parches o Data Dragon, y cuando haga falta saber en qué
  documento vive una definición. Es la skill que fija el ALCANCE y rutea a la documentación:
  para el detalle técnico deriva a `draftsense-backend`, `draftsense-frontend` y
  `agregacion-estadistica`.
---

# DraftSense — contexto del proyecto

Aplicación web pública donde jugadores de League of Legends responden preguntas cortas sobre
campeones. Las respuestas se agregan con métodos estadísticos establecidos y producen una medición
continua por campeón, versionada por parche y con intervalos de confianza reportables.

Reemplaza el etiquetado manual de 7 tags binarios, hecho por un único anotador, que hoy usa la línea
de investigación del Laboratorio DHARMa para su modelo de predicción de resultados de partidas.

## El guardarraíl de alcance

**DraftSense mide campeones. No analiza partidas.**

No hay `match_features.csv`, no hay `build_match_features`, no hay features por partida, no se
consume el dataset de partidas del laboratorio, no se integra con el modelo predictivo y no se
interpretan resultados. La frontera de la práctica es el CSV.

La salida son **tres archivos más un informe**: `champion_features` (una fila por campeón, 126
columnas, 20 magnitudes medidas), `matchup_matrix` (campeón_a × campeón_b × rol, 12 columnas),
`duo_features` (por dupla, 18 columnas) y el Informe de Calidad de Datos.

La métrica de impacto es **20 magnitudes continuas por campeón con IC y soporte muestral frente a
7 etiquetas binarias**. No es "~117 features por partida frente a 14": esa formulación es del
alcance viejo.

> **El Informe Inicial firmado por ambos tutores compromete `match_features.csv` y las 117
> features, y no hay que creerle en ese punto.** La `DraftSense_Especificacion_Tecnica.md` (fuera
> del repo) decía lo mismo, pero desde el 08/09/2026 lleva una nota de erratas que lo declara sin
> efecto y remite acá. El recorte está justificado en
> [ADR-005](../../../docs/13-adr/ADR-005-alcance-medicion-de-campeones.md) y debe registrarse en el
> Informe de Avance de la semana 6. El informe firmado no se toca.

## Cómo trabajar

1. **El documento va antes que el código.** La especificación de una funcionalidad se escribe en
   `docs/` antes de implementarla, no después. Si vas a implementar algo cuyo documento está
   `pendiente`, el documento es la primera tarea.
2. **Un documento en `v1` es contrato.** Cambiarlo exige anotar el cambio y, si contradice una
   decisión ya tomada, un ADR nuevo que la reemplace. Estados:
   `pendiente` → `borrador` → `v1` → `vN`.
3. **Toda decisión de diseño no obvia se registra como ADR** en `docs/13-adr/`. El documento de
   especificación dice *qué* y *cómo*; el ADR dice *por qué* y qué se descartó.
4. **Idioma:** documentación y comentarios en español; código, identificadores y textos de la
   interfaz pública en inglés (ADR-010).
5. **Ante ambigüedad, preguntar.** Si un dato no está en ningún documento o dos documentos se
   contradicen, preguntar antes de avanzar. No inventar valores, fórmulas ni requisitos.

## Cuándo leer cada referencia

- **`references/mapa-documentacion.md`** — antes de buscar cualquier cosa en `docs/`. Es una tabla
  *pregunta → documento y sección*, más el estado real de cada documento. Evita leer 347 KB para
  encontrar un dato.
- **`references/invariantes.md`** — antes de proponer un cambio de diseño o de responder "por qué
  está hecho así". Las 14 ADR resumidas en una línea cada una, y las contradicciones vivas del
  proyecto.
- **`references/cronograma.md`** — antes de estimar, de planificar una semana o de decidir si algo
  ya debería estar hecho. Tiene el estado real del avance.

## Verificación

```bash
cd backend && ruff check . && mypy app && pytest -q
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
python infra/check_docs.py
```

`check_docs.py` valida tres cosas que se rompen solas: que el DDL de `11-modelo-de-datos.md` parsee
como Postgres válido y sus FK e índices apunten a tablas existentes, que ningún enlace interno entre
documentos esté roto, y que los conteos de columnas de `26-esquema-de-salida.md` cierren. **Si
agregás un documento o movés un enlace, corré esto antes de dar por cerrado el trabajo.**

## Mantener esta skill al día

Esta skill **rutea** a `docs/`; nunca es la fuente de verdad de algo que ya está documentado. Eso es
deliberado: sin duplicación no hay deriva. Lo que sí posee y hay que mantener:

| Cuándo | Qué actualizar |
|---|---|
| Cambió el título o las secciones de un documento | `references/mapa-documentacion.md` |
| Un documento pasó de `pendiente` a `v1` | `mapa-documentacion.md` y `docs/README.md` |
| Se agregó o reemplazó un ADR | `references/invariantes.md` |
| Cerró una semana del cronograma | `references/cronograma.md` |
| Cambió el alcance | este archivo, `invariantes.md` y `../../../CLAUDE.md` |

Un hook avisa al editar `docs/**` o el `README.md` del repo.
