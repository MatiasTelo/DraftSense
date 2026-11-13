# 33 — Privacidad y aspectos legales

> Estado: **borrador** · Ola 5 · Redactado el 13/11/2026 · **Pendiente de aprobación del alumno**
>
> Es un borrador, no un contrato: no se implementan las pantallas `/about` y `/privacy` hasta que
> pase a `v1`. Lo que está en §1 a §3 **describe el sistema tal como es** y sale del esquema y del
> código. Lo que está en §4 a §6 son **textos y decisiones propuestos**, y §7 lista lo que este
> documento no puede decidir solo.

Qué guarda DraftSense de quien responde, qué no guarda, qué se le dice, y bajo qué condiciones usa
el material de Riot Games. Requerimientos que cubre: RF-003, RF-004, RF-006 y RNF-05.

---

## 1. Qué se guarda de una persona

Todo lo que el sistema sabe de alguien vive en dos tablas, `respondents` y `responses`
([`11-modelo-de-datos.md`](11-modelo-de-datos.md) §3.7 y §3.9), más `rankings` para el tipo 1.

| Dato | Dónde | De dónde sale | Para qué |
|---|---|---|---|
| Identificador interno | `respondents.respondent_id` | Lo genera el servidor, al azar | Unir las respuestas de una misma sesión |
| Hash del token de sesión | `respondents.session_token_hash` | SHA-256 del token de la cookie | Reconocer la cookie. El token en claro no se guarda ([ADR-001](13-adr/ADR-001-sin-autenticacion.md)) |
| Huella | `respondents.fingerprint_hash` | SHA-256 de user-agent, resolución y profundidad de color de pantalla, y un hash de la IP | Sólo para detectar muchas identidades creadas desde un mismo lugar ([`22-calidad-de-datos.md`](22-calidad-de-datos.md) §6) |
| Hash de la IP | `respondents.ip_hash` | HMAC-SHA-256 de la IP con una sal secreta | Sólo para el límite de tasa por IP ([ADR-033](13-adr/ADR-033-limite-por-hash-de-ip-con-sal.md)). Sin sal configurada no se guarda |
| Rango, rol principal y horas por semana | `declared_rank`, `declared_main_role`, `declared_hours_bucket` | Los declara la persona en `/start`; los tres son opcionales | Comparar respuestas entre segmentos. No ponderan ([`25-agregacion.md`](25-agregacion.md) §3) |
| Alias | `respondents.alias` | Lo genera el servidor (dos palabras y un número) | Mostrarlo en la tabla de posiciones. No se deriva de nada de la persona |
| Contadores y rachas | `answers_count`, `current_streak`, `last_seen`, … | Se actualizan al responder | Perfil, rachas y tabla de posiciones |
| Indicadores de calidad | `trust_score`, `honeypot_*`, `retest_*`, `fast_answers`, `straightline_runs`, `is_flagged` | Los calcula el sistema | Ponderar y filtrar en la agregación. **Nunca salen de la API** (RF-207) |
| Respuestas | `responses.answer`, `response_time_ms`, `created_at` | Lo que la persona contesta y cuánto tarda | Es el dato que se recolecta |

## 2. Qué no se guarda

- **Ni nombre, ni email, ni cuenta de Riot, ni ningún identificador de otro servicio.** No hay
  registro ni login (RF-006, ADR-001).
- **Ni la dirección IP en claro**, en ninguna tabla ni en ningún campo. De la IP sólo existen los
  dos hashes de §1.
- **Ni el token de sesión**: sólo su SHA-256.
- **Ni el idioma elegido** en el servidor: el selector `EN | ES` lo recuerda el navegador
  ([ADR-028](13-adr/ADR-028-idioma-por-parametro.md)).
- No se usa la API de Riot Games ni se consulta ningún dato de la cuenta de juego de nadie
  (RF-W02, RF-W03).
- No hay analítica de terceros, ni publicidad, ni píxeles de seguimiento en la aplicación.

Lo que **no** se puede afirmar, y por eso el texto público de §4 no lo dice:

- Que la huella sea «irreversible» sin matices. `fingerprint_hash` es un hash sin sal: quien tenga
  un volcado de la base y conozca el user-agent y la resolución de alguien puede probar las IPv4
  una por una. Es un riesgo acotado —no hay con qué asociar la fila a una persona— pero existe.
  `ip_hash` sí lleva sal y no tiene ese problema mientras la sal no se filtre.
- Que nada permita distinguir a una persona de otra: dentro del sistema las respuestas de una
  sesión están unidas por `respondent_id`. Lo que no hay es forma de saber **quién** es.

## 3. Qué queda en el navegador

| Qué | Dónde | Cuánto dura | Para qué |
|---|---|---|---|
| Cookie `ds_session` | Cookie `HttpOnly; Secure; SameSite=Lax` | 180 días | Es la sesión anónima: sin ella no se pueden unir las respuestas ni mostrar el progreso |
| Idioma elegido | `localStorage` | Hasta que la persona lo borre | Recordar `EN` o `ES` |

Es una sola cookie, propia y estrictamente necesaria para que el sitio funcione. No hay cookies de
terceros.

## 4. Texto público propuesto: `/privacy`

La interfaz es en inglés primero y español después ([ADR-010](13-adr/ADR-010-interfaz-en-ingles.md)).
Estos son los textos **propuestos**; no están en el código.

**English**

> **Privacy**
>
> DraftSense has no accounts. We don't ask for your name, your email or your Riot account, and we
> never store your IP address.
>
> **What we keep.** Your answers and how long each one took. If you choose to tell us, your rank,
> main role and hours played per week. A random alias shown on the leaderboard. Two one-way hashes
> derived from your browser and connection, used only to limit abuse.
>
> **What stays in your browser.** One cookie, `ds_session`, that keeps your progress for 180 days,
> and your language choice. No third-party cookies, no ads, no trackers.
>
> **What it's for.** Your answers are combined with everyone else's to describe each champion
> statistically, for research at the DHARMa Lab, UTN Mendoza. Published results are aggregates:
> no individual answer and no individual respondent appears in them.
>
> **Your choices.** The questions about you are optional. Clearing your cookies ends your session:
> we can no longer link new answers to the old ones, and neither can you.

**Español**

> **Privacidad**
>
> DraftSense no tiene cuentas. No te pedimos nombre, email ni tu cuenta de Riot, y nunca guardamos
> tu dirección IP.
>
> **Qué guardamos.** Tus respuestas y cuánto tardaste en cada una. Si eliges contarlo, tu rango,
> tu rol principal y tus horas de juego por semana. Un alias al azar que aparece en la tabla de
> posiciones. Dos hashes de una sola vía derivados de tu navegador y tu conexión, que sólo se usan
> para limitar el abuso.
>
> **Qué queda en tu navegador.** Una cookie, `ds_session`, que conserva tu progreso durante 180
> días, y el idioma que elegiste. Sin cookies de terceros, sin publicidad, sin rastreadores.
>
> **Para qué.** Tus respuestas se combinan con las de todos los demás para describir
> estadísticamente a cada campeón, en una investigación del Laboratorio DHARMa de la UTN Mendoza.
> Los resultados publicados son agregados: no aparece ninguna respuesta individual ni ningún
> respondedor individual.
>
> **Tus opciones.** Las preguntas sobre ti son opcionales. Borrar las cookies termina tu sesión: ya
> no podemos unir respuestas nuevas con las anteriores, y tú tampoco.

## 5. Texto público propuesto: `/about`

**English**

> **About**
>
> DraftSense asks League of Legends players short questions about champions — who has more
> engage, when a champion peaks, who wins a lane — and turns thousands of answers into a
> measurement of each champion, with its uncertainty stated.
>
> It is a research project of the DHARMa Lab at UTN Facultad Regional Mendoza, built as a
> supervised professional practice in Information Systems Engineering.
>
> There are no right answers. We want to know what players think.

**Español**

> **Acerca de**
>
> DraftSense hace preguntas cortas sobre campeones a jugadores de League of Legends —quién tiene
> más engage, cuándo llega al pico un campeón, quién gana una línea— y convierte miles de
> respuestas en una medición de cada campeón, con su incertidumbre a la vista.
>
> Es un proyecto de investigación del Laboratorio DHARMa de la UTN Facultad Regional Mendoza,
> desarrollado como Práctica Profesional Supervisada de Ingeniería en Sistemas de Información.
>
> No hay respuestas correctas. Queremos saber qué piensan los jugadores.

Las dos pantallas llevan al pie el aviso de §6.

## 6. Riot Games y Data Dragon

DraftSense usa los nombres y los retratos de los campeones, que son de Riot Games. Los retratos y
el catálogo salen de **Data Dragon**, el CDN público de Riot ([`10-arquitectura.md`](10-arquitectura.md)
§5); no se usa la API de Riot ni hace falta una clave.

El aviso que ya figura en el `README.md` del repositorio:

> DraftSense no está afiliado, respaldado ni patrocinado por Riot Games. *League of Legends* y sus
> activos son propiedad de Riot Games, Inc.

Para la aplicación pública se propone el aviso estándar que Riot pide a los proyectos de la
comunidad, en inglés, al pie de `/about` y `/privacy`:

> DraftSense isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games
> or anyone officially involved in producing or managing Riot Games properties. Riot Games, and
> all associated properties are trademarks or registered trademarks of Riot Games, Inc.

**Ese texto está citado de memoria y hay que cotejarlo con la política vigente de Riot antes de
publicarlo** (ver §7).

## 7. Lo que falta decidir

Este documento no pasa a `v1` hasta cerrar estos puntos. Ninguno se puede derivar del repositorio.

| # | Qué | Por qué no está resuelto |
|---|---|---|
| 1 | **Aprobar los textos de §4 y §5**, en inglés y en español | Son una propuesta; el tono y el alcance de lo que se promete son decisión del alumno y de los tutores |
| 2 | **Responsable y contacto** | Una política de privacidad nombra quién responde y cómo escribirle. No hay ninguna dirección de contacto definida para el proyecto |
| 3 | **Marco legal aplicable** | Si corresponde encuadrarlo en la Ley 25.326 de Protección de Datos Personales y qué exige en este caso —datos sin identificación directa, recolectados para investigación— lo tiene que confirmar quien corresponda en la Facultad o el laboratorio. Este borrador no afirma cumplimiento de ninguna norma |
| 4 | **Cuánto tiempo se conservan los datos** | El esquema no borra nada: `responses` es append-only ([ADR-002](13-adr/ADR-002-responses-append-only.md)) y no hay ningún plazo definido |
| 5 | **Pedidos de borrado** | No hay cómo borrar las respuestas de una sesión, por la misma razón, ni cómo acreditar que un pedido viene de esa sesión sin la cookie. Hay que decidir si se promete algo y qué |
| 6 | **Aviso de cookies** | La única cookie es estrictamente necesaria. Si alcanza con explicarla en `/privacy` o hace falta un aviso al entrar depende del punto 3 |
| 7 | **Condiciones de uso del material de Riot** | Cotejar el aviso de §6 y las condiciones de Data Dragon con la política vigente de Riot para proyectos de la comunidad |
| 8 | **Licencia de los datos entregados** | Bajo qué condiciones recibe y puede publicar el laboratorio los seis CSV y el Informe de Calidad de Datos. Es una decisión del laboratorio |
| 9 | **Hash sin sal en `fingerprint_hash`** | §2 lo señala como riesgo acotado. Pasarlo a un hash con sal, como `ip_hash`, cambiaría la huella de todos los respondedores existentes; hay que decidir si se hace antes del piloto |

---

Ver el índice en [`README.md`](README.md) y las decisiones ya cerradas en [`13-adr/`](13-adr/).
