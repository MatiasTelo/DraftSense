# ADR-029 — Cambiar de idioma traduce la cola en vez de descartarla

> Estado: **aceptada** · Fecha: 07/11/2026 · Sustituye en parte a
> [ADR-028](ADR-028-idioma-por-parametro.md): el punto 5 de la decisión

## Contexto

[ADR-028](ADR-028-idioma-por-parametro.md) §5 decidió que, al cambiar de idioma, **se descarta la
cola** de preguntas ya cargadas y se pide un lote nuevo, porque las de la cola vinieron armadas por
el servidor en el idioma anterior y el cliente no compone textos ([`12-api.md`](../12-api.md) §1.1).

En la prueba de la semana 9 el alumno lo encontró como un error: **al cambiar de idioma cambia la
pregunta**. La persona estaba leyendo un ranking, toca `ES` para entenderlo mejor y aparece otra
tarjeta. Lo que se buscaba era leer *esa* pregunta en el otro idioma.

El servidor no puede volver a servirla por `GET /questions/next`: el sampler no repite lo que el
cliente tiene en cola (ADR-020), y aunque pudiera, servirla otra vez movería posiciones y
cadencias. Hace falta otro camino.

## Decisión

1. **Un endpoint nuevo re-arma la cola en otro idioma**: `GET /questions/queued?ids=…&lang=…`
   ([`12-api.md`](../12-api.md) §2.8). Recibe los `question_id` de la cola, en orden, y devuelve las
   mismas preguntas con los textos en el idioma pedido, en el mismo orden, con el mismo formato que
   `GET /questions/next`.
2. **Es de sólo lectura y no pasa por el sampler.** No elige nada, no materializa, no abre ni
   consume cadencias de honeypots ni de retests, no toca `exposure_count` ni ninguna columna, y no
   hace commit. Es `render()` sobre preguntas que ya existen.
3. **El tipo 1 vuelve con su ranking ya servido**: el ranking pendiente más reciente de ese
   respondedor con esa ancla, con el mismo `ranking_id` y los cinco campeones en el mismo orden.
4. **Se omite lo que no corresponde**: ids que no existen, ya contestados por ese respondedor
   —salvo el retest pendiente, que por definición repite una contestada— y, en el tipo 1, anclas
   sin un ranking pendiente de ese respondedor. **El parche no filtra**: una pregunta de un parche
   recién reemplazado sigue siendo contestable ([ADR-024](ADR-024-activacion-explicita-de-parche.md),
   las respuestas en vuelo se aceptan), así que también se traduce.
5. **El cliente reemplaza cada pregunta por su versión traducida sin desmontar la tarjeta**: la
   `key` por `question_id` no cambia, así que el orden del ranking, el minuto del slider y los
   atributos marcados se conservan. Las que el servidor omitió salen de la cola. El lote que
   estuviera en vuelo en el idioma anterior se descarta y la precarga sigue en el nuevo.
6. **Si el pedido falla, la cola queda como estaba**, en el idioma anterior: la interfaz ya cambió y
   el lote siguiente llega en el nuevo. Perder la pregunta, que es lo que se quiere evitar, sería
   peor que verla un rato más en el otro idioma.

Los puntos 1 a 4, 6 y 7 de ADR-028 siguen vigentes.

## Alternativas consideradas

- **Dejar la tarjeta actual en el idioma anterior** y pedir sólo el resto en el nuevo. Es sólo
  frontend, pero la interfaz cambiaría de idioma y el enunciado no, que es justo la situación que
  la persona quería resolver.
- **Mandar los dos idiomas en cada pregunta.** El cambio sería instantáneo y sin endpoint, pero
  duplica el tamaño de cada lote para todos, cuando el cambio de idioma se usa una vez por sesión, y
  cambia la forma de la respuesta de `GET /questions/next`.
- **Un parámetro en `GET /questions/next`** que repita la cola traducida. Mezclaría en un mismo
  endpoint algo que elige y escribe (el sampler) con algo que sólo lee, y cualquier error en la
  bandera abriría o consumiría cadencias por accidente.

## Consecuencias

- El contrato suma un endpoint (`12-api.md` §2.8) y `frontend/src/api.ts` lo refleja.
- Cualquiera con una sesión puede pedir el texto de una pregunta por su id. No expone nada que el
  respondedor no pueda ver contestándola: el render no incluye si es honeypot ni ningún dato de
  calidad (RF-202).
- Un ranking con la misma ancla servido dos veces —posible si el cliente descartó la cola con la
  versión anterior— vuelve como el más reciente, que es el que la cola actual tiene.
