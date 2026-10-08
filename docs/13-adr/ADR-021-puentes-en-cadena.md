# ADR-021 — Los puentes del grafo se materializan como una cadena de k−1 preguntas

> Estado: **aceptada** · Fecha: 16/09/2026

## Contexto

[ADR-008](ADR-008-conectividad-por-componentes.md) decidió que un job, `check_graph_connectivity`,
calcule las componentes conexas del grafo de comparaciones de cada dimensión y marque
`bridge_priority = true` en las preguntas que unirían componentes separadas. El sampler sirve esas
preguntas antes que cualquier otra ([`21-sampler.md`](../21-sampler.md) §4.2).

`bridge_priority` es una columna de `questions`, así que **para marcar una pregunta, la fila tiene
que existir**. Pero las preguntas se generan de forma perezosa (RF-111, 21 §2): la fila aparece
cuando el sampler sirve la pregunta. Las que unirían dos componentes son justamente las que nadie
sirvió todavía, y por eso casi nunca existen.

El caso extremo es el arranque. Sin respuestas, cada campeón habilitado es una componente propia:
con los 58 del tier 1 hay 58 componentes. Marcar todos los pares entre componentes serían
C(58, 2) = 1 653 preguntas por dimensión, 13 224 en las ocho: la precomputación que RF-111
prohíbe.

## Decisión

**En cada corrida, por cada dimensión activa, el job mantiene como mucho k−1 puentes válidos,
donde k es la cantidad de componentes.** Los pasos:

1. **El grafo.** Los nodos son los campeones habilitados (`is_active` y `pool_tier` dentro de
   `sampler.enabled_pool_tiers`). Las aristas son las respuestas de tipo 1 del parche vigente en esa
   dimensión, con `choice` igual a `a` o `b`, que pasan los filtros de
   [`25-agregacion.md`](../25-agregacion.md) §1: respondedor no marcado, `trust_score` mayor o igual
   a `export.min_trust`, pregunta que no es honeypot y respuesta que no es retest.
2. **Las componentes**, con union-find.
3. **Desmarca** `bridge_priority` en las preguntas de la dimensión cuyos dos campeones ya quedaron
   en la misma componente o dejaron de estar habilitados.
4. **Cuenta los puentes que siguen marcados como aristas tentativas**: unirán componentes cuando
   alguien los conteste. Con ellas vuelve a calcular las componentes.
5. **Materializa los que faltan.** Si todavía queda más de una componente, las ordena al azar y
   crea una pregunta entre cada par de componentes consecutivas, con un campeón al azar de cada
   una, y la marca `bridge_priority = true`. Si la combinación elegida resulta ser una honeypot, se
   vuelve a sortear; y si las dos componentes son de un solo campeón —el caso del arranque, donde
   sortear otra vez da el mismo par—, la cadena sigue con la próxima componente del orden que sí
   se pueda unir. Si la última de la cadena no se une con ninguna de las que faltan, la próxima se
   engancha a una componente anterior. Sin esto, cada honeypot del catálogo podía dejar a su
   dimensión sin un puente.

En el arranque, con el tier 1, son 57 preguntas por dimensión y 456 en total. A partir de ahí la
cantidad de puentes válidos nunca pasa de k−1 por dimensión.

## Alternativas consideradas

- **Marcar sólo las filas que ya existen.** No crea nada, pero las filas existentes que unen dos
  componentes son sólo las que alguien recibió y no contestó, o contestó con `unknown`. El efecto es
  casi nulo, y la conectividad queda librada a la rama de exploración.
- **Marcar todos los pares entre componentes.** Son 13 224 filas en el arranque, contra RF-111, y
  llenarían el índice `questions_sampler` de preguntas que nadie va a contestar.
- **Una estrella hacia la componente mayor.** También alcanza con k−1 preguntas, pero hace que la
  componente mayor sea parte de todos los puentes y les da a sus campeones un lugar privilegiado:
  es la asimetría que ADR-008 rechazó al descartar los campeones ancla. La cadena en orden aleatorio
  trata igual a todas las componentes.

## Consecuencias

- **Mientras el grafo esté partido, casi todo el tipo 1 que se sirve son puentes, por encima de ε**,
  porque en el pseudocódigo de 21 §10 el puente va antes que la exploración. En el lanzamiento
  cerrado de la semana 7, con ε = 1, las primeras respuestas de tipo 1 recorren la cadena. Sigue
  siendo un muestreo simétrico —ningún campeón se elige de antemano—, pero no es el sorteo uniforme
  de [ADR-012](ADR-012-sampler-uniforme-en-arranque-en-frio.md) hasta que el grafo queda conectado.
  Se declara acá para que no se lea como un desvío.
- **Una corrida puede conectar una dimensión entera** si todos sus puentes se contestan con `a` o
  `b`. Un puente contestado `unknown` no es arista y sigue marcado para el próximo respondedor.
- **La tabla crece acotada**: como mucho k−1 filas nuevas por dimensión por corrida, y las marcadas
  se reusan mientras sigan haciendo falta.
- **Las aristas son sólo del parche vigente.** La agregación usa una ventana de parches
  ([ADR-004](ADR-004-ventana-de-parches-con-decaimiento.md)), así que el job puede ver partida una
  dimensión que, con la ventana completa, está conectada. Es el lado conservador del error.
- **Las respuestas bajo `export.min_trust` no conectan**, igual que no van a entrar a la agregación.
- La cantidad de componentes por dimensión es el dato que necesitan el criterio de 21 §7.2 —grafo
  conectado en al menos 6 de las 8 dimensiones— y el panel de la semana 7.
