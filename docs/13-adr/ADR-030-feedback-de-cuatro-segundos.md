# ADR-030 — El feedback dura 4 segundos y se saltea con un toque

> Estado: **aceptada** · Fecha: 07/11/2026 · Sustituye la fila «Duración del feedback» de
> [`30-ux-flujos.md`](../30-ux-flujos.md) §10

## Contexto

[`30-ux-flujos.md`](../30-ux-flujos.md) §5.1 y §10 fijaron que el feedback post-respuesta se
superpone **1,2 segundos** y después entra la tarjeta siguiente: «suficiente para leer el
porcentaje, corto para no romper el ritmo».

En la prueba de la semana 9 el alumno lo encontró corto. Desde las semanas 6 y 8 el cartel dice
más cosas que un porcentaje: el feedback por pares del ranking
([ADR-022](ADR-022-tipo-1-ranking-de-cinco.md)), las siete barras del tipo 5, las barras apiladas
del 2v2 y el mensaje de dos líneas de soporte bajo. En 1,2 s no se alcanza a leer, y el feedback es
el gancho de retención principal del producto.

## Decisión

1. **El cartel dura 4 segundos** y después entra la tarjeta siguiente, igual que antes.
2. **Un toque o un clic en cualquier parte del cartel lo saltea**: entra la tarjeta siguiente en
   ese momento.
3. **En escritorio también lo saltean `Enter` y `Espacio`** (la regla de teclado de 30 §9). Se
   ignora la tecla mantenida (`repeat`) y la que cae sobre un botón o un enlace con foco, que el
   navegador ya convierte en un clic de ese botón.
4. **Vale para todas las variantes del cartel**, incluido «You're one of the first to answer
   this».
5. **El cartel no dice que se puede tocar.** No hay texto de aviso: se descubre usándolo.
6. Saltear y esperar hacen exactamente lo mismo, una sola vez: el cartel se cierra y la cola avanza.

## Alternativas consideradas

- **Mantener 1,2 s.** Es lo que la prueba encontró insuficiente.
- **4 s sin poder saltear.** Quien ya leyó el resultado esperaría tres segundos por tarjeta: con
  40 respuestas por sesión, dos minutos parados.
- **Cerrar sólo con un toque, sin tiempo.** Obliga a una acción extra en cada tarjeta y rompe el
  ritmo de quien responde rápido.
- **Un aviso «Tap to continue».** Considerado y descartado por el alumno.
- **Cualquier tecla saltea.** Un `1`–`5` apretado para saltear se confundiría con responder la
  tarjeta siguiente.

## Consecuencias

- El ritmo baja para quien no toca: una sesión de 40 respuestas suma hasta 2 minutos más de
  feedback. Es el costo aceptado; quien quiere ir rápido toca.
- La racha y los contadores no cambian: se actualizan con la respuesta, no con el cierre del cartel.
- Un doble toque rápido sobre una opción puede saltear el cartel en cuanto aparece. No registra
  nada ni pierde la respuesta: sólo se ve menos tiempo el resultado.
