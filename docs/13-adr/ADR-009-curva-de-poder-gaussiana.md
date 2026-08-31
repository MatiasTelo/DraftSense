# ADR-009 — Curva de poder gaussiana a nivel campeón

> Estado: **aceptada** · Fecha: 31/08/2026

## Contexto

El tipo 2 recolecta un único número por campeón: el minuto en que alcanza su pico de poder. La
dimensión temporal es lo que el laboratorio señaló como la línea más prometedora para la próxima
etapa, y está completamente ausente del etiquetado actual.

Un solo número es poco para alimentar un modelo. Lo que resulta útil es un **perfil temporal**:
cuánto de su poder tiene disponible un campeón en distintos momentos de la partida.

## Decisión

Se deriva una curva de poder por campeón a partir de su `peak_minute`, con forma de campana
gaussiana:

```
power_at(t) = exp( -(t - peak_minute)² / (2 · σ²) )
```

con `σ` global, calibrado sobre los datos del piloto y registrado en `exports`. Se exporta evaluada
en cinco cortes: `power_at_5`, `power_at_10`, `power_at_15`, `power_at_20`, `power_at_25`.

Es una transformación **a nivel campeón**, no de equipo: agregar por equipo es del laboratorio
([ADR-005](ADR-005-alcance-medicion-de-campeones.md)).

## Alternativas consideradas

- **Rampa lineal con meseta**, `power(t) = min(1, t / peak)`. Más simple e interpretable, pero
  afirma que un campeón de *early game* conserva su poder máximo en el minuto 40. Eso es falso, y
  además **borra exactamente la señal que se quiere medir**: que estar fuerte temprano implica estar
  débil tarde. Una curva monótona creciente hace que todos los campeones se parezcan al final de la
  partida.
- **Triangular.** Captura el decaimiento sin exponenciales, pero el quiebre en el pico es un
  artefacto sin correlato en el juego y complica la derivada.
- **Sigmoide.** Adecuada para campeones de escalado, pésima para los de *early game*: nunca decae.
- **Preguntar la curva directamente**, con varias preguntas de slider por campeón. Datos mucho
  mejores a un costo de recolección varias veces mayor, sobre una muestra que ya es el cuello de
  botella.

## Consecuencias

- Las cinco columnas `power_at_*` son una **transformación determinista** de `peak_minute`, no cinco
  mediciones independientes. Se documenta explícitamente para que nadie las trate como evidencia
  adicional.
- `σ` es un parámetro global, no por campeón: se asume que todos los campeones tienen una ventana de
  poder de ancho similar, lo cual es una simplificación conocida. Un hipercarry y un campeón de
  presión temprana probablemente no la tengan.
- Se calcula del lado de DraftSense, no del laboratorio, para que la definición sea única y quede
  registrada junto al resto de los parámetros de la corrida.
- El valor de `σ` se calibra sobre el piloto y su sensibilidad se reporta en el Informe de Calidad
  de Datos.
