# ADR-001 — Sin autenticación: sesión anónima por cookie

> Estado: **aceptada** · Fecha: 31/08/2026

## Contexto

DraftSense necesita miles de respuestas de jugadores voluntarios, sin recompensa material. El
riesgo número uno del proyecto es la participación insuficiente durante el piloto. Cada paso entre
que alguien abre el enlace y responde su primera pregunta pierde una fracción de los visitantes, y
un formulario de registro es el paso más caro de todos.

Al mismo tiempo el sistema necesita identidad persistente para tres cosas: no repetir preguntas ya
respondidas, sostener la racha y el perfil, y acumular el historial que alimenta el trust score.

## Decisión

No hay registro ni inicio de sesión. La identidad es una **sesión anónima** que viaja en una cookie
`ds_session` — `HttpOnly`, `Secure`, `SameSite=Lax`, 180 días. En la base se guarda sólo el SHA-256
del token; el token en claro vive únicamente en el navegador del usuario.

No se almacena email, nombre, IP en claro ni identificador de cuenta de Riot.

## Alternativas consideradas

- **Registro con email.** Identidad sólida y recuperable, pero mata la conversión y obliga a tratar
  datos personales, con todo lo que eso implica en consentimiento y resguardo.
- **Login con cuenta de Riot (OAuth).** Permitiría verificar el rango declarado en vez de confiar en
  lo que el usuario dice. Requiere aprobación de Riot para una app de producción y un flujo de
  autorización completo: semanas de trabajo para un beneficio que el trust score cubre parcialmente.
- **Sin identidad alguna.** Elimina el trust score, el test-retest y la gamificación, que son
  justamente los mecanismos que sostienen la calidad y la retención.

## Consecuencias

- La conversión de visitante a respondedor es la máxima posible: se responde la primera pregunta
  a un toque de distancia.
- El rango declarado **no es verificable**. Se trata como variable de segmentación, nunca como
  filtro de calidad, y el análisis de estabilidad entre segmentos reporta si importa o no.
- Borrar las cookies equivale a empezar de cero: se pierden racha, perfil e historial. Es un costo
  aceptado; qué se le muestra al usuario en ese caso se define en `23-gamificacion.md`.
- La deduplicación depende de `fingerprint_hash`, que es evadible por un usuario decidido. Se
  complementa con honeypots y rate limiting ([ADR-002](ADR-002-responses-append-only.md)).
