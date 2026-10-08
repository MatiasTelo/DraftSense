# ADR-020 — Las cadencias de calidad y lo pendiente se guardan en el servidor

> Estado: **aceptada** · Fecha: 16/09/2026 · Ampliada el 17/09/2026 (honeypot pendiente y `queued`)

## Contexto

El módulo de calidad intercala dos clases de pregunta que no pasan por la función de prioridad
([`21-sampler.md`](../21-sampler.md) §6):

- **Honeypots**, una cada 10 a 15 preguntas. La posición «se sortea al abrir cada ventana, no se
  fija», y la cadencia se lleva por respondedor contra `answers_count`
  ([`22-calidad-de-datos.md`](../22-calidad-de-datos.md) §3.6).
- **Retests**, uno cada 30, que repiten una pregunta contestada hace 15 o más (22 §4). La repetición
  se guarda como una fila nueva con `is_retest_of` apuntando a la original.

Faltaban tres cosas para implementarlo, y ningún documento las resolvía:

1. **Dónde vive la posición sorteada.** `respondents` no tenía ninguna columna para ella, y
   sortearla en cada lote la haría distinta en cada petición.
2. **Cómo sabe `POST /responses` que una respuesta es un retest.** El cuerpo es
   `{question_id, answer, response_time_ms}` ([`12-api.md`](../12-api.md) §2.4) y no tiene ningún
   campo para marcarlo. El cliente tampoco puede saberlo: cuáles preguntas eran retests es
   información que nunca se muestra ([`23-gamificacion.md`](../23-gamificacion.md) §3). Sin embargo,
   CA-204 exige un `409` para la repetición común —el doble toque— y CA-205 exige aceptar el retest
   con `is_retest_of` ([`03-criterios-aceptacion.md`](../03-criterios-aceptacion.md) §3). Para el
   índice `responses_one_per_question` las dos son la misma pregunta respondida dos veces.
3. **En qué posición cae cada pregunta de un lote.** Lo encontró la prueba de punta a punta en
   staging, el 17/09. El cliente pide el lote siguiente cuando todavía le quedan dos tarjetas por
   contestar (`30-ux-flujos.md` §8), así que la pregunta `k` del lote nuevo no cae en
   `answers_count + k`, sino dos posiciones después. Con la primera versión de esta decisión eso
   producía dos defectos:
   - **Honeypots dobles.** Si una de las dos tarjetas en cola era la honeypot, su cadencia seguía
     vencida y el lote nuevo traía otra (en staging, en las posiciones 59 y 61).
   - **Cadencias estiradas.** La ventana se abre con la posición real y se chequeaba con la
     estimada, así que cada intervalo sumaba dos: honeypots cada 12 a 17 y retests cada 32, con lo
     que CA-301 podía fallar.

## Decisión

**El servidor guarda el estado en cuatro columnas nulables de `respondents`, y el cliente le dice
qué preguntas tiene en cola.**

| Columna | Qué guarda |
|---|---|
| `next_honeypot_at` | La posición a partir de la cual toca la próxima honeypot |
| `next_retest_at` | La posición a partir de la cual toca el próximo retest |
| `pending_honeypot` | La honeypot que se sirvió y todavía no se contestó |
| `pending_retest_of` | La respuesta original que el sampler sirvió como retest y todavía no se contestó |

**Posición** es el índice, contando desde cero, de la respuesta dentro de la historia del
respondedor.

- **`GET /questions/next` acepta `queued`**: los `question_id` que el cliente tiene en su cola
  sin contestar al pedir el lote (hasta 10). La primera pregunta del lote ocupa la posición
  `answers_count + len(queued)`, y cada una de las siguientes, la próxima. **El lote nunca incluye
  una pregunta de `queued`**: sin esa regla, el puente de mayor prioridad —que es determinista— se
  volvía a servir mientras el cliente lo tenía en cola, y si se contestaba mientras viajaba el lote
  aparecía dos veces (en staging, dos `409` en 30 respuestas).
- **Apertura perezosa de las ventanas.** Con `NULL`, el sampler abre la primera ventana al servir el
  primer lote: `next_honeypot_at = answers_count + g − 1`, con `g` sorteado uniforme en
  `quality.honeypot_every`, y `next_retest_at = answers_count + quality.retest_every − 1`. Así un
  respondedor nuevo recibe la primera honeypot entre la posición 9 y la 14, y el primer retest en
  la 29. Los respondedores anteriores a esta decisión empiezan a contar desde donde están.
- **La ventana siguiente se abre al registrar la respuesta.** Si la honeypot se contesta en la
  posición `p`, pasa a `p + g` con un `g` nuevo; si el retest se contesta en `p`, pasa a
  `p + retest_every`. Una honeypot contestada `unknown` no suma intento (22 §3.5), pero también abre
  la ventana: si no la abriera, la persona recibiría honeypots seguidas y el mecanismo se delataría.
- **Lo pendiente bloquea y se reintenta.** Al servir una honeypot o un retest, el sampler lo anota
  como pendiente, y mientras siga pendiente no se elige otro.
  - Si el cliente lo tiene en cola (su `question_id` está en `queued`), el lote no trae ni ése ni
    otro.
  - Si el cliente lo perdió —una recarga llega sin él en `queued`—, se vuelve a servir en su lugar.
  - Un pendiente que ya no se puede servir (la honeypot se retiró, un campeón salió del pool) se
    descarta y se elige otro.
- **Vencida hasta que se sirva.** Una cadencia toca cuando la posición es mayor o igual que la
  guardada. Si no se puede servir —no hay catálogo, el respondedor ya vio todas las honeypots del
  parche o no tiene ninguna respuesta elegible para repetir—, la posición se llena con una pregunta
  común y la cadencia queda vencida, así que se reintenta en la posición siguiente. Como máximo se
  sirven una honeypot y un retest por lote. Si las dos caen en la misma posición, gana la honeypot
  (21 §6) y el retest pasa a la siguiente.
- **`POST /responses`.** Contestar la honeypot pendiente limpia `pending_honeypot`. Si
  `pending_retest_of` apunta a una respuesta de la misma `question_id`, la marca se limpia con un
  `UPDATE … WHERE pending_retest_of = :original`. Si esa sentencia afecta una fila, la respuesta se
  inserta con `is_retest_of = :original`. En cualquier otro caso se inserta como respuesta común y,
  si ya existía, el índice la rechaza con `409`.

«Marcada como retest», en CA-204, CA-205 y en `12-api.md` §3, quiere decir marcada por el servidor
de esta forma.

## Alternativas consideradas

- **Inferir el retest por distancia.** Sin columnas nuevas: una repetición a 15 o más posiciones
  de la original sería un retest, y una más cercana, un `409`. Se descartó porque cualquier cliente
  conoce su propia historia y puede reenviar preguntas viejas a propósito. Cada una sumaría a
  `retest_consistent` y subiría el trust, que es el peso de todas sus respuestas.
- **Un token de entrega en el contrato.** `/questions/next` devolvería un identificador opaco por
  pregunta y el cliente lo reenviaría en el `POST`. Para no delatar cuál es el retest, todas las
  preguntas tendrían que llevar token, y el cliente tendría que guardarlos y reenviarlos: mucho más
  cambio que `queued` para resolver lo que el servidor puede saber por su cuenta.
- **Derivar las posiciones sin estado**, con un generador pseudoaleatorio sembrado con el
  `respondent_id`. `POST /sessions` devuelve ese identificador, así que quien conozca el esquema
  podría predecir dónde caen las honeypots, que es justo lo que 22 §3.6 quiere evitar.
- **Abrir la ventana al servir, sin honeypot pendiente.** Evita las dobles sin columna nueva, pero
  una honeypot perdida en una recarga no se reintenta, y un script que recargue después de las
  primeras tarjetas de cada lote podría esquivarlas.
- **Compensar la precarga en el servidor** —adelantar la primera ventana dos posiciones— sin
  cambiar el contrato. Ata el servidor a una constante del frontend (`PREFETCH_AT`) sin que nada lo
  declare: un cambio en la cola rompería las cadencias en silencio.
- **`queued` como cantidad y no como lista.** Fue la primera versión del parámetro. Da la posición,
  pero no dice cuáles preguntas tiene el cliente: el servidor seguía mandando repetidos, el cliente
  los descartaba, y en ese lote las posiciones quedaban corridas una o dos.
- **Una tabla de preguntas servidas.** Resolvería lo mismo que `queued` sin tocar el contrato, pero
  crece con cada lote y no distingue una recarga de una precarga.

## Consecuencias

- Migración `0003` con las cuatro columnas, y el DDL de
  [`11-modelo-de-datos.md`](../11-modelo-de-datos.md) §3.7 actualizado. No hay datos personales
  nuevos (CA-004).
- **El contrato suma un parámetro opcional**, `queued`, en `12-api.md` §2.3. Un cliente que no lo
  mande sigue funcionando: sólo pierde la exactitud de las posiciones y puede recibir repetidos. Un
  valor falso no sirve para esquivar honeypots: la cadencia vencida se sirve en la primera posición
  que la alcance, y declarar como «en cola» una honeypot que no se tiene sólo la posterga hasta el
  lote siguiente. Más de 10 ids se rechaza.
- `GET /questions/next` pasa a escribir en `respondents`, algo que los permisos del rol de
  aplicación ya admitían (11 §4).
- Dos lotes simultáneos del mismo respondedor pueden elegir cada uno un retest. Gana la última
  escritura; el otro retest, al contestarse, devuelve `409` y el cliente avanza sin mostrar nada
  (CA-502). Se pierde un retest; no entra ningún dato malo.
- Un doble toque sobre un retest produce una fila de retest y un `409`, gracias al `UPDATE`
  condicional.
- `queued` viaja en la URL. Son identificadores de preguntas, no datos de la persona.
- `next_honeypot_at` y `next_retest_at` son sorteos: a diferencia de los contadores de calidad, no
  se pueden reconstruir exactamente desde `responses`. No hace falta: son un cronograma, no una
  medición.
