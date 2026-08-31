# ADR-010 — Interfaz en inglés primero, español después

> Estado: **aceptada** · Fecha: 31/08/2026

## Contexto

El riesgo número uno del proyecto es no conseguir suficientes respuestas. La difusión prevista
apunta a comunidades de jugadores: r/leagueoflegends y r/summonerschool por un lado, servidores de
Discord hispanohablantes por otro.

Los dos primeros son **órdenes de magnitud más grandes** que cualquier comunidad hispanohablante de
*League of Legends*, y su idioma es el inglés. La terminología del juego, además, es inglesa incluso
entre jugadores hispanohablantes: nadie dice "potencial de aislar y matar un objetivo", dicen *pick*.

## Decisión

La interfaz pública se construye **en inglés desde el día 1**. El español se agrega vía
internacionalización hacia la semana 8, antes de la difusión en los canales hispanohablantes.

La documentación técnica y los informes de la práctica se escriben en español; el código, los
identificadores y los textos de la interfaz, en inglés.

El esquema lo contempla desde el inicio: `dimensions` y `traits` tienen `label_en` obligatorio y
`label_es` nulable, de modo que agregar el español es cargar datos, no migrar.

## Alternativas consideradas

- **Bilingüe desde el día 1.** Abre todos los canales a la vez, pero agrega trabajo de i18n en la
  semana 3, que es cuando hay que dejar operativo el primer tipo de pregunta de punta a punta.
  Retrasa el camino crítico por un beneficio que llega igual cuatro semanas después.
- **Sólo español.** Limita la difusión al segmento chico y pone en riesgo directo la meta de
  respuestas.

## Consecuencias

- La muestra potencial es la máxima posible, que es lo que más importa para la calidad de los datos.
- El **segmento de rango declarado puede quedar sesgado** hacia la población angloparlante durante
  las primeras oleadas. Es observable —el análisis de estabilidad por segmento está justamente para
  eso— y se corrige cuando entra el canal hispanohablante.
- La i18n queda como trabajo planificado de la semana 8, con el esquema ya preparado.
- Los enunciados de las preguntas se redactan en inglés con la terminología nativa del juego, lo que
  además reduce la ambigüedad frente a una traducción.
