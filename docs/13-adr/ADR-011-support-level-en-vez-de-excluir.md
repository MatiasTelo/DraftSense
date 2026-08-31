# ADR-011 — Exportar todo con `support_level`, no excluir bajo umbral

> Estado: **aceptada** · Fecha: 31/08/2026

## Contexto

Con el volumen esperado del piloto, una parte de las estimaciones va a tener soporte muestral
escaso e intervalos de confianza anchos. Hay que decidir qué hacer con ellas al armar el CSV.

Excluirlas produce un archivo más limpio, pero con la meta comprometida de 1 000 respuestas podría
producir uno casi vacío. Exportarlas sin ninguna señal invita a que alguien las use como si valieran
lo mismo que las bien sostenidas.

## Decisión

**Se exporta todo.** Cada magnitud lleva su valor, su intervalo de confianza al 95 %, su soporte
muestral `_n` y una columna `_support` con tres niveles: `solid`, `limited`, `insufficient`,
calculados a partir de `_n` y del ancho del intervalo con umbrales por tipo de magnitud
(ver `26-esquema-de-salida.md` §2.4).

Una magnitud sin ningún dato se escribe como **celda vacía**, nunca como `0`, con `_n = 0` y
`_support = insufficient`.

## Alternativas consideradas

- **Excluir por debajo de un umbral.** CSV más limpio de leer, pero toma en nombre del laboratorio
  una decisión que es del laboratorio, y con umbrales que todavía no están calibrados. Además hace
  invisible la diferencia entre "medimos y salió incierto" y "no medimos".
- **Exportar sólo valor e intervalo, sin juicio.** Máximo respeto por el límite de alcance, pero les
  traslada un cálculo repetitivo que quien construyó el instrumento está mejor posicionado para
  hacer.

## Consecuencias

- El laboratorio filtra con su propio criterio y **nada se pierde en silencio**.
- La distinción entre celda vacía y `0` es crítica y se documenta de forma prominente: `0` en la
  columna `engage` significa "engage promedio del pool", vacío significa "sin datos". Confundirlas
  metería ruido sistemático en cualquier modelo.
- Los umbrales de `_support` son un juicio calibrable, no un hecho. Se revisan con los datos reales
  del piloto y el valor usado queda registrado en `exports`.
- El CSV es más ancho, con cinco a siete columnas por magnitud medida. Es un costo trivial para un
  archivo de a lo sumo 170 filas.
