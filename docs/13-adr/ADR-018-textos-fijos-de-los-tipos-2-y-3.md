# ADR-018 — Los textos de los tipos 2 y 3 viven en el backend, no en la base

> Estado: **aceptada** · Fecha: 16/09/2026

## Contexto

[`20-tipos-de-pregunta.md`](../20-tipos-de-pregunta.md) §1.2 dice que el texto de las definiciones
«vive en las tablas `dimensions` y `traits`, no en el código», y
[CA-506](../03-criterios-aceptacion.md) pide que la definición que despliega el ícono `?` salga «de
la base y no del código» para **cualquier** pregunta con concepto medido.

La regla se escribió pensando en los dos **catálogos** del sistema. Una dimensión o un atributo
nuevo se agrega insertando una fila (RF-603, CA-601), y por eso su enunciado y su definición
tienen que estar en esa misma fila: si estuvieran en el código, agregar una dimensión exigiría un
despliegue.

Los tipos 2 y 3, que se implementan en la semana 4, no tienen catálogo. Cada uno mide **un único
concepto fijo** —el minuto de pico, el enfrentamiento de línea al minuto 10— y su enunciado, su
definición, la escala del slider y las cinco etiquetas del enfrentamiento sólo figuran literales en
[`12-api.md`](../12-api.md) §2.3. Ninguna tabla los contiene y ninguna migración los prevé.

## Decisión

**El enunciado, la ayuda, la escala del slider y las plantillas de las opciones de los tipos 2 y 3
son constantes del backend**, en `backend/app/services/question_texts.py`.

- El servidor sigue componiendo el texto final, con los nombres de campeón ya sustituidos, así que
  [`12-api.md`](../12-api.md) §1.1 se cumple igual: el cliente nunca ve una plantilla.
- CA-506 y 20 §1.2 se leen como lo que son: reglas sobre los catálogos `dimensions` y `traits`.
- Los límites del slider se importan de la validación del `answer`, no se repiten: la escala que se
  muestra y la que se acepta no pueden divergir.
- La misma regla alcanza a la variante 2v2 del tipo 3 y al tipo 4, que llegan en la semana 8 con el
  mismo problema. No hace falta otro ADR para ellos.

## Alternativas consideradas

- **Una tabla nueva** (`question_type_copy` o similar). Cumple CA-506 al pie de la letra, pero
  exige una migración, un seed y una superficie de administración para textos que sólo cambian
  junto con el maquetado de la tarjeta: cambiar «wins hard» sin cambiar la escala de cinco niveles
  no tiene sentido.
- **Claves en `app_settings`.** Se editan sin desplegar, pero `app_settings` es el estado
  operativo del sistema —umbrales, pesos, tiers— y mezclar textos ahí ensucia la única tabla que el
  panel de administración expone para cambiar comportamiento.
- **Pseudo-filas en `dimensions`.** Reutiliza las columnas `prompt_en` y `description_en`, pero el
  sampler del tipo 1 las sortearía como dimensiones comparables.
- **Textos en el frontend.** Rompe [`12-api.md`](../12-api.md) §1.1 y parte la internacionalización
  de la semana 8 en dos lugares ([ADR-010](ADR-010-interfaz-en-ingles.md)).

## Consecuencias

- Cambiar uno de estos textos requiere un despliegue. Es aceptable: un cambio en el enunciado de
  una pregunta es un cambio de metodología —altera qué contesta la gente— y corresponde que quede en
  el historial de git.
- El español de la semana 8 entra en el mismo módulo, junto a las constantes en inglés.
- CA-506 sigue verificándose tal cual para el tipo 1 y el tipo 5; para los tipos 2 y 3 se verifica
  que la ayuda llegue del servidor, no que salga de una tabla.
