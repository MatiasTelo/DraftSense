# ADR-033 — El límite por IP cuenta sobre un hash con sal, y la sesión se crea sólo si el pedido sale bien

> Estado: **aceptada** · Fecha: 13/11/2026

## Contexto

RF-209 y [`12-api.md`](../12-api.md) §4 piden limitar la tasa de respuestas «por respondedor **y
por hash de IP**». Desde la semana 2 sólo existía la primera mitad: el docstring de
`services/responses.py` decía que la segunda «no está implementada» porque `responses` no guarda
nada derivado de la IP, y ningún documento registraba el desvío.

La revisión general del 13/11/2026 mostró por qué importa. Los endpoints que necesitan identidad
crean la sesión al vuelo cuando el pedido llega sin cookie (12 §1.3). Un script que no guarda la
cookie recibe **un respondedor nuevo por pedido**, y el límite por respondedor no lo frena nunca:
cada identidad manda una sola respuesta. Cada una nace con trust `0.500`, por encima de
`export.min_trust`, así que esas respuestas entran a la agregación. La única defensa era el job de
huellas duplicadas, que es diario y se dispara a mano.

La misma prueba mostró un segundo efecto: **un pedido sin cookie que termina en error igual dejaba
creado un respondedor vacío**. Ocho pedidos de `curl`, varios con `400`, crearon ocho filas.

Lo único derivado de la IP que guarda el esquema es `fingerprint_hash`, donde el hash de la IP
entra mezclado con el user-agent y la resolución (RF-004): no sirve para contar por IP, porque
cambiar el user-agent cambia la huella.

## Decisión

1. **`respondents.ip_hash`** (migración `0007`), nulable: el HMAC-SHA-256 de la IP con la que se
   creó el respondedor, con una **sal secreta** que vive sólo en el entorno (`DS_IP_HASH_SALT`,
   en `backend/.env`). La IP en claro sigue sin guardarse en ningún lado.
2. **Sin sal configurada no se guarda nada**: `ip_hash` queda en `NULL` y el límite por IP no se
   aplica. La API lo avisa en el log al arrancar. Un hash sin sal de una IPv4 se revierte
   recorriendo los 2³² valores posibles, así que guardarlo sería guardar la IP.
3. **El límite por IP** cuenta los **envíos** ([ADR-022](ADR-022-tipo-1-ranking-de-cinco.md)) de
   **todos los respondedores creados desde ese `ip_hash`**. Se evalúa después del límite por
   respondedor y responde el mismo `429 rate_limit_exceeded`. Sigue sin Redis: cuenta sobre
   `responses`.
4. **Sus dos topes son parámetros**, `quality.ip_rate_per_minute` y `quality.ip_rate_per_day`
   ([`22-calidad-de-datos.md`](../22-calidad-de-datos.md) §8), que arrancan en los valores de
   RF-209 —40 y 1 500— y se cambian desde el panel sin desplegar. Los del límite por respondedor
   siguen siendo los fijos de RF-209.
5. **La sesión creada al vuelo se confirma sólo si el pedido termina bien.** El respondedor nuevo
   se inserta dentro de la transacción del pedido y se confirma al final; si el pedido termina en
   error se revierte, y la respuesta de error no lleva `Set-Cookie`. Un `POST /sessions` exitoso
   crea la sesión como siempre.
6. Los respondedores anteriores a la migración quedan con `ip_hash` en `NULL` y sólo los alcanza
   el límite por respondedor.

## Alternativas consideradas

- **Anotar el desvío y dejarlo para el despliegue** (un límite en el proxy o el firewall del
  laboratorio). Descartada por el alumno: RF-209 es prioridad M y el servidor del laboratorio
  todavía no está definido.
- **Hash simple de la IP, sin sal**, como el que entra en la huella. No pide una variable nueva,
  pero un volcado de la base permitiría recuperar las IP por fuerza bruta, y RNF-05 pide que el
  esquema no tenga datos personales identificables.
- **Guardar el hash en `responses`.** Contaría por la IP de cada respuesta y no por la de creación,
  pero agrega una columna a la tabla más grande y a la única append-only, por cada fila.
- **Contar por `fingerprint_hash`.** Se evade cambiando el user-agent.
- **Dejar los topes por IP fijos en el código**, iguales a los del respondedor. Es la lectura
  literal de RF-209, pero obliga a desplegar para difundir el piloto en una red compartida.
- **Borrar el respondedor vacío después de un error.** Deja una ventana en la que la fila existe
  y obliga a un `DELETE` fuera de la transacción del pedido.

## Consecuencias

- **RNF-05 sigue cumpliéndose, con una condición nueva:** `ip_hash` no es reversible *mientras la
  sal no se filtre*. La sal es una credencial: va en `backend/.env`, nunca en el repositorio, y
  cambiarla desvincula a los respondedores ya creados de su IP (sus conteos por IP arrancan de
  cero).
- **Una red compartida comparte el límite.** Varias personas detrás de la misma IP —un aula, el
  wifi de la facultad— suman al mismo contador. Con el valor inicial de 40 por minuto y el ritmo
  esperado de unas 10 respuestas por minuto por persona, cuatro personas a la vez lo alcanzan.
  Por eso los topes por IP son parámetros (punto 4): **antes de difundir el piloto en un aula hay
  que subirlos desde el panel.** Cuánto, depende de cuánta gente comparta la red, y no está
  decidido acá.
- El límite cuenta por la IP **de creación** del respondedor, no por la de cada respuesta: quien
  cambia de red sigue contando en la primera. Alcanza para el caso que motiva la decisión, el del
  script sin cookie, donde las dos coinciden.
- Detrás de un proxy la IP sale de `X-Forwarded-For`. Si el proxy no sobrescribe esa cabecera, el
  cliente puede falsearla y evitar el límite: queda como requisito de
  [`32-despliegue.md`](../32-despliegue.md).
- `pyproject.toml` pasa a exigir `fastapi>=0.121`: la confirmación al final del pedido usa
  `Depends(..., scope="function")`, que hace que ocurra **antes** de enviar la respuesta. Sin eso
  el navegador podría mandar el pedido siguiente con una cookie que la base todavía no conoce.
- Notas fechadas el 13/11 en [`01-requerimientos.md`](../01-requerimientos.md) (RF-209),
  [`11-modelo-de-datos.md`](../11-modelo-de-datos.md) §3.7 y [`12-api.md`](../12-api.md) §1.3 y §4.
