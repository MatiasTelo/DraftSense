# ADR-027 — El tipo 5 exige marcar al menos un atributo

> Estado: **aceptada** · Fecha: 29/10/2026

## Contexto

[`20-tipos-de-pregunta.md`](../20-tipos-de-pregunta.md) §6 definía `{"traits": []}` como una
respuesta válida que significa «ninguno de estos», y CA-207 la convertía en criterio de
aceptación. [`25-agregacion.md`](../25-agregacion.md) §1.4 y §5.6 la sumaban al denominador de los
siete atributos y al numerador de ninguno.

Al planificar la semana 8, que es cuando el tipo 5 se implementa de punta a punta, el alumno
decidió lo contrario: **para confirmar hay que marcar al menos un atributo**. La lista vacía dejaba
además dos huecos sin definir: la consistencia del retest entre dos listas vacías (el índice de
Jaccard de ∅ contra ∅ no está definido, [`22-calidad-de-datos.md`](../22-calidad-de-datos.md) §4) y
si una respuesta vacía era candidata a retest, cuando 22 §4 sólo retestea respuestas «con una
opción definida».

## Decisión

**Una respuesta de tipo 5 tiene que marcar entre uno y siete atributos.**

1. **API.** `{"traits": []}` responde `400 answer_shape_mismatch`, igual que cualquier otra forma
   inválida.
2. **Base.** El `CHECK responses_answer_shape` exige `jsonb_array_length(answer -> 'traits') >= 1`
   (migración `0006`): `responses` es append-only y un dato mal formado no se puede corregir
   después ([ADR-002](ADR-002-responses-append-only.md)).
3. **Interfaz.** *Confirm* queda deshabilitado mientras no haya ningún atributo marcado.
4. **Agregación.** `p̂(c, T)` se calcula igual, sobre respuestas que marcaron algo: el
   denominador son las respuestas de tipo 5 al campeón con `T` activo, y ninguna está vacía.
5. **Retest.** El caso ∅ contra ∅ deja de existir. Toda respuesta de tipo 5 es candidata a retest
   y es consistente con la anterior si el índice de Jaccard es ≥ 0.60 (22 §4).

**Sustituye** la fila `traits: []` de 20 §6 (payload y casos borde), CA-207 y las menciones a la
lista vacía de 25 §1.4 y §5.6.

## Alternativas consideradas

- **Mantener `[]` como «ninguno de estos».** Es lo que decía la especificación. Separa «no aplica
  ninguno» de «no respondió», pero deja indefinido el retest y su información la aporta igual la
  dimensión del tipo 1 con su `unknown_rate`.
- **Agregar una opción explícita *None of these*.** Conserva la información sin la lista vacía,
  pero suma un octavo botón a una tarjeta que ya tiene siete y vuelve a abrir la pregunta de cómo
  se retestea.

## Consecuencias

- La proporción de un atributo es ahora **entre quienes marcaron al menos uno**. Un campeón al que
  casi nadie le reconoce ninguno de los siete atributos tendrá proporciones más altas que con la
  definición vieja. El Informe de Calidad de Datos de la semana 10 tiene que decirlo al describir
  `champion_traits`.
- Desaparece la información «ninguno de estos». Si el laboratorio la necesitara, haría falta un
  ADR nuevo con la opción explícita.
- Ninguna fila existente se ve afectada: el tipo 5 no se sirvió antes de la semana 8.
