# ADR-032 — El movimiento de la interfaz se hace sólo con CSS

> Estado: **aceptada** · Fecha: 08/11/2026

## Contexto

Hasta la semana 10 la interfaz no tenía transiciones: una tarjeta reemplazaba a la otra de golpe,
los botones no respondían al puntero y el feedback aparecía entero de una vez. El alumno pidió que
los botones y las tarjetas «tengan más vida» con animaciones básicas, para que responder resulte
más atractivo.

El bundle inicial tiene un presupuesto de 200 KB gzip que CI hace cumplir (RNF-03).

## Decisión

1. **Todo el movimiento se hace con CSS**: transiciones y `@keyframes` declarados como tokens en
   el bloque `@theme` de `frontend/src/tokens.css` (`--animate-*`,
   [ADR-017](ADR-017-tailwind-como-sistema-de-estilos.md)). Ninguna dependencia nueva.
2. Se anima: el estado de los controles (hover, presión, selección), la entrada de cada pantalla,
   la entrada de cada tarjeta y sus opciones, el feedback post-respuesta (aparición, barras que se
   llenan) y el fondo del landing.
3. **Ninguna animación bloquea la entrada.** Las opciones se pueden tocar mientras entran, y las
   entradas duran 250 ms o menos. El `response_time_ms` se sigue midiendo desde el montaje de la
   tarjeta (RF-109).
4. **El feedback lleva una barra de tiempo**: una línea que se vacía en los 4 s del cartel
   ([ADR-030](ADR-030-feedback-de-cuatro-segundos.md)). Su duración sale de la misma constante que
   el temporizador (`FEEDBACK_MS`), y **no dice que se puede tocar** (ADR-030, punto 5).
5. **`prefers-reduced-motion: reduce` apaga el movimiento**: las animaciones y transiciones quedan
   instantáneas y la barra de tiempo no se muestra. Nada de lo que se anima lleva información que
   no esté también quieta en pantalla.
6. Los realces no usan sombras: la esquina biselada es un `clip-path`, que recorta el
   `box-shadow`. Se usan color de fondo y de borde, brillo y `transform`.

## Alternativas consideradas

- **`framer-motion`.** Permite animar también la *salida* de la tarjeta y las transiciones entre
  rutas, pero pesa unos 30–40 KB gzip —una porción grande del presupuesto de RNF-03— para efectos
  que CSS resuelve.
- **Animar la salida de la tarjeta con CSS.** Obliga a retrasar el desmontaje y a mantener dos
  tarjetas vivas; choca con la `key` por pregunta de `Play` y con los candados contra el doble
  envío. La salida ya la tapa el cartel de feedback.
- **Animar la racha y el contador.** Considerado y no elegido por el alumno.

## Consecuencias

- El presupuesto de bundle no se mueve: el costo es CSS.
- La entrada de la tarjeta depende de que `Play` la monte con `key={question_id}`: anima con cada
  pregunta nueva y **no** al cambiar de idioma, que conserva la tarjeta
  ([ADR-029](ADR-029-cambiar-de-idioma-traduce-la-cola.md)).
- jsdom no ejecuta animaciones: los tests verifican la estructura (la barra de tiempo y su
  duración), no el movimiento. El movimiento se revisa a mano.
