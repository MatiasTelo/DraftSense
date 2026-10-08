# ADR-022 — El tipo 1 es un ranking de cinco campeones que se guarda como diez comparaciones

> Estado: **aceptada** · Fecha: 08/10/2026

## Contexto

Hasta la semana 5, una tarjeta de tipo 1 mostraba **dos** campeones y una dimensión ("Who has more
engage?"), y cada toque producía una comparación. En la reunión del lunes 05/10/2026 el tutor de la
organización, Marinozi, pidió que la tarjeta muestre **cinco campeones para ordenar**. Un orden
total de cinco implica C(5, 2) = 10 comparaciones pareadas, y de esas diez el backend tiene que
**guardar cada una por separado**: si el usuario ordena en *poke* `Jax < Gragas < Gnar < LeBlanc <
Lux`, se registran `Jax < Gragas`, `Jax < Gnar`, `Jax < LeBlanc`, … hasta las diez.

El modelo de agregación no cambia: Bradley-Terry estima a partir de comparaciones pareadas
([ADR-003](ADR-003-bradley-terry.md)), y un ranking es exactamente un paquete de ellas. Lo que
cambia es cómo se sirve, cómo se responde y cómo se guarda, y eso toca a todo lo que hasta ahora
suponía "una pregunta de tipo 1 = un par": honeypots, retest, consenso, conectividad, rate limit,
contador de respuestas y *straightlining*.

## Decisión

**Cada uno de los diez pares sigue siendo su propia pregunta de tipo 1, y el ranking es un envío
que produce diez filas en `responses`.** Todo lo que ya funciona por par —`answer_counts`, entropía,
cobertura, aristas del grafo, agregación— sigue funcionando sin cambios.

1. **Tabla `rankings`.** Cuando el sampler sirve un tipo 1 crea una fila con el respondedor, el
   parche, la dimensión, los cinco campeones en el orden en que se muestran y el **par ancla**. Al
   contestar se completa `submitted_order`. Las diez filas de `responses` llevan el mismo
   `ranking_id` (migración `0004`).
2. **El par ancla** es el par que el sampler habría servido antes: el puente, la honeypot, el retest
   o el elegido por explotación o exploración ([`21-sampler.md`](../21-sampler.md)). A él se suman
   **tres campeones al azar** del pool habilitado. El `question_id` del ítem es el del ancla, así
   que `queued`, la honeypot pendiente y el retest pendiente siguen identificándose por pregunta
   ([ADR-020](ADR-020-estado-de-cadencias-en-el-servidor.md)). El ancla nunca es un par de otro
   ranking pendiente —en la cola del cliente o en el mismo lote—, porque contestar primero ése la
   dejaría respondida.
3. **La respuesta** es `{"order": [id, id, id, id, id]}`, de más a menos, o `{"choice": "unknown"}`.
   El backend materializa los diez pares en forma canónica y guarda en cada uno `{"choice": "a"}` si
   `champion_a` quedó arriba de `champion_b`, o `"b"` si no. *Not sure* vale para el ranking entero
   y se guarda como diez `unknown`, para que `D_unknown_rate` siga teniendo sentido.
4. **Pares repetidos.** Si el respondedor ya había contestado alguno de los nueve pares no ancla en
   otro ranking, esa fila se ignora (`ON CONFLICT DO NOTHING` sobre `responses_one_per_question`) y
   se guardan las demás. El sampler **no** evita esos pares al elegir los tres extra.
5. **Un ranking cuenta como una respuesta**: suma 1 a `answers_count`, a las rachas, a la mezcla de
   la sesión y al rate limit. Las diez filas son detalle de almacenamiento. Las consultas que cuentan
   respuestas de un respondedor cuentan **envíos**: la fila del ancla, o la fila sin ranking.
6. **Honeypot.** Una honeypot del catálogo se sirve como par ancla y se evalúa **sólo ese par**,
   contra `expected_answer`, como antes. Los tres campeones extra se sortean de modo que ningún otro
   par del ranking sea una honeypot en esa dimensión, y si con los reintentos no alcanza, la fila de
   ese par no se guarda: una honeypot sólo se contesta como ancla.
7. **Retest.** Se toma un ranking ya contestado (no `unknown`) y su **par de las puntas**: el que el
   usuario puso primero contra el que puso último. Ese par se vuelve a servir como ancla con tres
   campeones al azar, y es consistente si queda en el mismo sentido que la respuesta anterior a ese
   par.
8. **Feedback.** Se cuentan los pares del ranking con al menos `sampler.consensus_threshold`
   respuestas y en cuántos coincide el usuario con la mayoría: *"You agree with the community on 7
   of 10 pairs"*. Si ninguno llega al umbral, se muestra el mensaje de "todavía no hay respuestas
   suficientes".
9. **Interacción.** Lista reordenable con arrastrar y soltar (`@dnd-kit`, con touch y teclado) más
   *Confirm*. Los cinco campeones llegan en orden aleatorio.
10. **El tipo 1 sale del *straightlining*.** Con cinco campeones en orden aleatorio y arrastre, "tocar
    siempre la misma posición" deja de ser un patrón definido. La regla queda sólo para el tipo 3.

## Alternativas consideradas

- **Una fila con el orden completo y una tabla aparte de comparaciones derivadas.** Respeta "una
  respuesta, una fila", pero obliga a reescribir sobre la tabla nueva el consenso, la entropía, la
  cobertura, la conectividad, las honeypots y el retest. Con las diez filas en `responses`, todo eso
  sigue igual.
- **Tocar los campeones en orden en vez de arrastrarlos.** Es más simple de implementar en móvil,
  pero el usuario eligió arrastrar y soltar por ser más directo visualmente.
- **Cinco campeones al azar.** Pierde la priorización por entropía y cobertura y, sobre todo, los
  puentes del grafo ([ADR-021](ADR-021-puentes-en-cadena.md)), que son los que garantizan que
  Bradley-Terry pueda ubicar a todos los campeones en una escala común.
- **Repetir el ranking completo como retest.** Da diez pares por retest y le daría al tipo 1 diez
  veces más peso en el trust que a los demás tipos. El par de las puntas es la comparación de la que
  el usuario está más seguro: si no la repite, contestó al azar.
- **Evitar los pares ya contestados al elegir los tres extra.** Restringe mucho las combinaciones
  posibles a medida que el respondedor avanza. Se prefirió servirlas y descartar en el backend sólo
  la fila repetida.

## Consecuencias

- **Diez comparaciones por tarjeta en vez de una**: con la misma cantidad de respuestas de tipo 1,
  el grafo de cada dimensión recibe diez veces más aristas y se conecta mucho antes.
- **Las comparaciones de un mismo ranking no son independientes**: son transitivas por
  construcción. Para el bootstrap de [`25-agregacion.md`](../25-agregacion.md) §5.1 la unidad de
  remuestreo sigue siendo la comparación. Es el mismo límite que 25 §4.7 ya declara para las
  comparaciones de una misma persona, y se decide con el mismo criterio y en la misma fecha.
- `responses` sigue siendo append-only ([ADR-002](ADR-002-responses-append-only.md)). `rankings` no
  lo es: `submitted_order` se completa al contestar.
- El rate limit, la variedad, el retest, el perfil y los patrones degenerados cuentan envíos y no
  filas. Toda consulta nueva que cuente respuestas de un respondedor tiene que hacer lo mismo.
- La tarjeta del tipo 1 necesita confirmación explícita, igual que las de los tipos 2 y 5.
- El catálogo de 34 honeypots ([ADR-013](ADR-013-honeypots-verificables-desde-el-kit.md)) no
  cambia.
