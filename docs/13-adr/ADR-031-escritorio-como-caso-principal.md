# ADR-031 — El escritorio es el caso principal; el celular sigue funcionando

> Estado: **aceptada** · Fecha: 08/11/2026 · Sustituye el primer punto de
> [`30-ux-flujos.md`](../30-ux-flujos.md) §9 («Móvil primero»)

## Contexto

[`30-ux-flujos.md`](../30-ux-flujos.md) §9 fijó el diseño **móvil primero**: la base es de 360 px
y el escritorio es el caso derivado, con la tarjeta centrada y un ancho máximo de 640 px. La
suposición era que la difusión por Reddit y Discord traería sobre todo tráfico de teléfonos.

El alumno espera ahora que la mayoría responda desde una PC. Con el diseño actual, en escritorio
la aplicación es una tira de 640 px con la tarjeta pegada arriba, un vacío debajo y la navegación
en el borde inferior de la ventana, lejos de la tarjeta.

## Decisión

1. **El escritorio (≥ 1024 px, el punto `lg` de Tailwind) es el caso que se diseña primero.**
2. En escritorio, el contenido de cada pantalla es **un panel de hasta 720 px**, centrado en
   vertical y en horizontal sobre el fondo, con borde.
3. En `/play`, `/me` y `/leaderboard` la **navegación (Play · Profile · Ranks) sube a la barra
   superior**, que en escritorio va a lo ancho de la ventana y suma la marca `Draftsense` a la
   izquierda. La barra inferior no se muestra en escritorio.
4. **Los cinco tipos de tarjeta no cambian por dentro**: siguen siendo una columna, con el mismo
   orden de opciones y los mismos controles.
5. **El celular sigue siendo requisito.** Debajo de 1024 px la aplicación se ve como hasta ahora:
   columna de hasta 640 px, barra inferior y 44 px de área táctil. RNF-06 (usable a 360 px sin
   scroll horizontal) no cambia.

## Alternativas consideradas

- **Tarjeta ancha en dos columnas** (~1000 px: enunciado y retratos a la izquierda, opciones a la
  derecha). Aprovecha más la pantalla, pero obliga a rediseñar los cinco tipos de tarjeta y el
  feedback, y separa la vista de la respuesta: el ojo cruza la pantalla en cada pregunta.
- **Sólo centrar en vertical**, con la misma columna y la barra inferior. Es el cambio mínimo y
  deja la navegación en el borde de la ventana.
- **Mantener móvil primero.** Contradice el público que se espera.

## Consecuencias

- La barra superior de escritorio lleva más que la racha y el contador: suma la marca y los tres
  destinos. Es una excepción más a «nada más» de [`30-ux-flujos.md`](../30-ux-flujos.md) §5, como
  el selector de idioma ([ADR-028](ADR-028-idioma-por-parametro.md)); la navegación ya estaba
  siempre visible, sólo cambia de lugar.
- Hay dos navegaciones en el código, una por tamaño. Sólo una se muestra a la vez (`display: none`
  en la otra), así que el lector de pantalla encuentra una sola.
- La regla de una pregunta por pantalla sin scroll se verifica ahora también a 1366 × 768, el
  escritorio más chico habitual, además de a 360 px.
