# ADR-003 — Bradley-Terry para los scores de dimensión

> Estado: **aceptada** · Fecha: 31/08/2026

## Contexto

Hay que producir un score continuo por campeón en cada dimensión funcional. Con 40 campeones en el
pool inicial y 8 dimensiones, el producto cartesiano de pares es de 780 por dimensión, 6 240 en
total; con el catálogo completo pasa de 10⁵. Ninguna cantidad realista de respuestas cubre todos
los pares.

Además, el instrumento tiene que ser cómodo para el respondedor. La pregunta se responde en cinco
segundos, desde un teléfono, sin pensar.

## Decisión

Se recolectan **comparaciones pareadas** ("¿quién tiene más engage: A o B?") y se ajusta un modelo
de **Bradley-Terry** por dimensión, ponderado por trust, usando `choix.ilsr_pairwise`. El intervalo
de confianza se obtiene por bootstrap sobre las comparaciones (2 000 remuestreos).

Para el tipo 3 se usa la generalización de **Rao-Kupper**, que admite empates y margen.

## Alternativas consideradas

- **Escala Likert directa** ("¿cuánto engage tiene Alistar, del 1 al 5?"). Más simple de agregar,
  pero las escalas absolutas sufren de uso idiosincrático: lo que para un jugador es 4 para otro es
  3, sin que ninguno esté equivocado. La comparación pareada elimina esa varianza porque no requiere
  que dos personas compartan una escala, sólo que ordenen igual.
- **Elo.** Es esencialmente Bradley-Terry ajustado en línea. Atractivo por su actualización
  incremental, pero depende del orden de llegada de las respuestas, no produce intervalos de
  confianza de forma natural y no es reproducible: reprocesar los mismos datos en otro orden da
  otro resultado. Para un dato que se entrega a un equipo de investigación, la reproducibilidad
  pesa más que la actualización en vivo.
- **Conteo simple de victorias.** Un campeón que sólo se comparó contra rivales débiles quedaría
  arriba. Bradley-Terry corrige por la fuerza del oponente, que es exactamente el problema cuando
  el muestreo de pares es desbalanceado.

## Consecuencias

- **Se estima un score por campeón a partir de comparaciones parciales**, sin necesitar que todos
  los pares se hayan observado. Esta propiedad es la que hace viable todo el proyecto.
- Los scores están en **log-odds**, sin cero natural: sólo tienen sentido relativos al pool. Se
  centran en 0 y la escala se documenta en `26-esquema-de-salida.md`.
- **El grafo de comparaciones debe estar conectado** o el modelo no tiene solución única. Es una
  restricción real y se resuelve en [ADR-008](ADR-008-conectividad-por-componentes.md).
- Las respuestas `unknown` se descartan del ajuste pero se registran: su tasa es una señal de
  validez de la dimensión para ese campeón.
