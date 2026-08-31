# ADR-006 — Pool de campeones escalonado, definido por un snapshot de pick rate

> Estado: **aceptada** · Fecha: 31/08/2026

## Contexto

El catálogo tiene unos 170 campeones. Con 8 dimensiones, para que el grafo de comparaciones quede
apenas conectado hacen falta ~1 360 pares distintos, y para que cada campeón tenga soporte decente,
del orden de 20 000 respuestas sólo de tipo 1. La meta comprometida del piloto es 1 000 respuestas
y la meta de trabajo, unos miles.

Repartir esa muestra sobre 170 campeones produce un CSV donde casi todo es `insufficient`: cobertura
completa y ningún dato usable.

## Decisión

El pool es **escalonado y parametrizado en base de datos**. La columna `champions.pool_tier` define
tres niveles: **1** núcleo (~40 campeones), **2** expansión (~80), **3** el resto. El sampler sólo
genera preguntas sobre los tiers habilitados. Promover un campeón es un `UPDATE`, no un despliegue.

La composición del núcleo sale de un **snapshot manual de pick rate**, tomado una vez por parche
desde una fuente pública de soloq (lolalytics o U.GG) y cargado como seed versionado en
`infra/seeds/`, junto con su fuente, su URL y su fecha, en las tablas `pick_rate_snapshots` y
`pick_rate_entries`.

## Alternativas consideradas

- **Frecuencia en el dataset de partidas del laboratorio.** Era el criterio original, pero cae junto
  con [ADR-005](ADR-005-alcance-medicion-de-campeones.md): ya no se consume ese dataset.
- **Scraping automático de lolalytics o U.GG.** Datos siempre frescos, a costa de una dependencia
  frágil —sin API oficial, sujeta a cambios de HTML— para algo que se necesita dos o tres veces en
  toda la práctica.
- **Oracle's Elixir.** CSV oficial, gratuito y citable, pero de juego profesional: el meta pro es
  más estrecho que el de soloq, que es donde juegan los respondedores.
- **Todos los campeones desde el día 1.** Cobertura completa e intervalos inservibles.

## Consecuencias

- El piloto cierra con datos **densos sobre pocos campeones** en vez de ralos sobre todos. Es el
  intercambio correcto: un score con intervalo angosto sobre 40 campeones es utilizable; 170 scores
  con intervalo de ancho 2 no lo son.
- La cobertura es **parcial y declarada de entrada**, no un hallazgo incómodo al final. El CSV
  incluye `pool_tier` en cada fila.
- Cero dependencia externa en runtime: el snapshot se carga una vez y vive en el repositorio, lo que
  además lo hace reproducible y auditable.
- Hace falta un criterio numérico para promover de tier durante el piloto. Se define en
  `21-sampler.md`.
