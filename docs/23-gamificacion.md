# 23 — Gamificación y retención

> Estado: **v1** · Última revisión: 01/09/2026 · Ola 3 · Desbloquea la semana 6 del cronograma

La gamificación de DraftSense no es un adorno: es **el instrumento de la meta M5** del Informe
Inicial —al menos 1 000 respuestas reales— y el único que hay, porque el sistema no paga, no tiene
usuarios cautivos y no puede obligar a nadie a contestar nada.

Requerimientos que implementa: RF-301 a RF-304.

---

## 1. La restricción que ordena todo el diseño

Cada mecánica de este documento se evalúa contra una sola pregunta: **¿empuja a responder más, o
empuja a responder de una manera determinada?**

La primera es el objetivo. La segunda destruye el dato. Un incentivo que premia *qué* se contesta
—y no cuánto— rompe la independencia entre anotadores, que es un supuesto del alfa de Krippendorff
y del modelo de Bradley-Terry. Si la gente contesta lo que cree que contestan los demás, el acuerdo
inter-anotador que después se reporta como evidencia de calidad **está inflado por construcción** y
no mide nada.

Por eso hay una regla dura que atraviesa todo el documento:

> **Ninguna recompensa depende del contenido de la respuesta.** Ni la racha, ni el perfil, ni la
> tabla de posiciones. Sólo del volumen y de la constancia.

---

## 2. Las dos rachas — RF-301

Hay **dos rachas y miden cosas distintas**, porque hay dos comportamientos distintos que hay que
sostener: que la sesión de hoy sea larga, y que haya sesión mañana.

### 2.1 `current_streak` — respuestas seguidas

Cuántas respuestas lleva **sin una pausa larga**. Se corta cuando pasan más de **30 minutos** entre
dos respuestas.

```
si  now() - respondents.last_seen > 30 minutos:  current_streak = 1
si no:                                           current_streak = current_streak + 1
best_streak = greatest(best_streak, current_streak)
```

Se actualiza en la misma transacción del `INSERT` de la respuesta, sobre columnas de la propia fila
del respondedor (`10-arquitectura.md` §3, paso 4). No cuesta una consulta extra.

Es el motor **intra-sesión**: es lo que convierte "contesté cinco y me aburrí" en "contesté
cuarenta". La interfaz la muestra en la barra superior y celebra los múltiplos de 10 con
`10 in a row 🔥` sobre el feedback normal (`30-ux-flujos.md` §5.1).

**Por qué 30 minutos y no el cierre de la pestaña:** el cierre no es observable desde el servidor sin
inventar un mecanismo de sesión activa, y castigaría a quien atiende el timbre en el medio. Media
hora es suficientemente largo para que una interrupción normal no corte la racha, y suficientemente
corto para que "seguidas" signifique algo.

### 2.2 `current_day_streak` — días seguidos

Cuántos **días consecutivos** con al menos **5 respuestas**. Es el motor **entre sesiones**, y es la
mecánica que sostiene la recolección a lo largo de las cuatro semanas del piloto: sin ella, un
respondedor entusiasta aporta 60 respuestas una tarde y no vuelve nunca.

```
hoy = fecha actual en America/Argentina/Buenos_Aires

si last_active_date <> hoy:
    answers_today   = 0
    last_active_date = hoy
answers_today = answers_today + 1

si answers_today == 5:                              # se cruza el umbral hoy
    si last_active_date_previa == hoy - 1 dia:  current_day_streak += 1
    si no:                                      current_day_streak  = 1
    best_day_streak = greatest(best_day_streak, current_day_streak)
```

**El umbral de 5 existe para que la racha signifique algo.** Con umbral 1, mantener la racha cuesta
un toque y deja de ser un compromiso; con un umbral alto se vuelve una obligación y la gente
abandona en cuanto la rompe una vez.

**El día se define en horario argentino, no en UTC**, y es deliberado: la difusión del piloto es
local, y en UTC alguien que responde a las 22:00 de un martes estaría sumando al miércoles. Una
racha que se rompe por un huso horario que el usuario no ve es una racha que se siente arbitraria.
La zona es un parámetro (`gamification.streak_timezone`) por si el piloto se difunde afuera.

### 2.3 Lo que la racha NO es

**No se cuenta racha por coincidir con el consenso.** Es la mecánica más tentadora del catálogo
—"5 aciertos seguidos"— y la peor posible acá: premiaría contestar lo que uno cree que contesta la
mayoría en vez de lo que cree que es cierto.

Es la misma razón por la que el feedback post-respuesta dice `You're in the 19%` y no `Wrong`
(`30-ux-flujos.md` §5.1). **En DraftSense no hay respuestas correctas**, y todo lo que sugiera que
las hay contamina la medición y la vuelve inservible para el propósito del laboratorio.

Queda escrito acá porque es el tipo de idea que reaparece cuando alguien mira las métricas de
retención a mitad del piloto y busca una palanca.

---

## 3. Qué se muestra: el perfil — RF-302

`GET /me` y la pantalla `/me` (`30-ux-flujos.md` §6):

| Dato | De dónde sale |
|---|---|
| Cantidad de respuestas | `respondents.answers_count` |
| Racha actual y mejor racha | `current_streak`, `best_streak` |
| Racha de días y mejor racha de días | `current_day_streak`, `best_day_streak` |
| Tasa de acuerdo con la comunidad | Proporción de respuestas que coincidieron con la mayoría, sobre las preguntas con soporte ≥ 20 |
| Percentil de contribución | Posición por `answers_count` sobre el total de respondedores no marcados |
| Cobertura por tipo | Conteo de respuestas por `question_type` |

**La tasa de acuerdo se muestra pero no se premia.** Es información sobre uno mismo —*"coincidís con
la comunidad el 78 % de las veces"*— y aparece sin juicio, sin meta, sin barra de progreso y sin
comparación con otros. Un respondedor con 55 % de acuerdo no ve nada que sugiera que le va peor que
uno con 90 %: en un instrumento de medición, el que disiente de forma consistente es tan valioso
como el que coincide.

**Lo que nunca se muestra:** el `trust_score`, el resultado de los honeypots, cuáles preguntas eran
honeypots, cuáles eran retests, y cualquier métrica de la que se pueda despejar alguna de esas cosas
(RF-207).

### 3.1 Quien borra las cookies

Pierde racha, perfil e historial. Es la consecuencia aceptada de no tener registro
([ADR-001](13-adr/ADR-001-sin-autenticacion.md)) y **no se intenta recuperar**: reconstruir la
identidad desde la huella sería usar para restaurar sesiones un dato que sólo se recolectó para
deduplicar, y contradiría de frente lo que promete `33-privacidad-y-legal.md`.

La interfaz lo dice de entrada, en el onboarding, en una línea: *"your progress lives in this
browser"*. Decirlo antes convierte una pérdida sorpresiva en una condición conocida.

---

## 4. El alias — RF-304

Autogenerado con la forma `adjetivo-sustantivo-NNNN`: `brave-poro-4417`, `calm-baron-0091`. Los
diccionarios son de términos del juego, viven en `infra/seeds/alias_words.yaml` y el sufijo numérico
resuelve las colisiones.

**Nunca es un identificador real.** No se deriva del `respondent_id` ni de la huella: es una columna
propia, asignada al crear la sesión, sin relación calculable con nada.

Se descartó dejar que el usuario lo elija. Un alias libre en una tabla pública **necesita
moderación**, y una práctica de 200 horas no puede sostener una cola de moderación ni asumir el
riesgo reputacional de que el trabajo del Laboratorio DHARMa aparezca con un insulto en pantalla.
El costo —que el alias no expresa nada— es trivial contra eso.

---

## 5. La tabla de posiciones — RF-303, RF-304

`GET /leaderboard?window=day|week|all`, top 50, ordenada por cantidad de respuestas de esa ventana.

### 5.1 Quién aparece

```sql
WHERE NOT is_flagged
  AND trust_score >= app_settings['export.min_trust']
```

Dos filtros, y el segundo es el que cambia respecto de la primera redacción de RF-304.

**El problema que resuelve.** Ordenar por cantidad de respuestas sin más deja un agujero de
incentivos: con el límite de 1 500 respuestas diarias, alguien que conteste basura a toda velocidad
**lidera la tabla**. Sus respuestas se descartan en el export por trust bajo, pero públicamente gana
— y la tabla de posiciones es el instrumento de M5. Estaríamos premiando en la pantalla principal
exactamente el comportamiento que el módulo de calidad existe para descartar.

Con el filtro, la tabla pasa a significar **"quién contribuyó al conjunto de datos"**, que es lo que
en realidad se quiere celebrar. Alguien cuyas respuestas no entran a ningún export tampoco contribuye
a la meta.

### 5.2 Por qué esto no viola RF-207

RF-207 prohíbe **exponer el trust score**. El filtro no lo expone: no publica el valor, no publica el
orden por trust, y no permite despejarlo de ninguna métrica visible. La tabla sigue ordenada por
cantidad de respuestas, que es un número que el usuario ya conoce de su propio perfil.

Lo que sí filtra es **un bit**: alguien que desaparece de la tabla puede inferir que está por debajo
del umbral. Se aceptó ese bit por tres razones:

1. Es **binario**, no el valor. No permite optimizar contra la métrica: no se puede saber si se está
   en 0.29 o en 0.05, ni qué acción lo movió.
2. Sólo alcanza a quien ya está respondiendo mal. Un respondedor nuevo arranca en `0.500`, muy por
   encima de `0.300`, y cruzar el umbral hacia abajo requiere fallar unas cinco honeypots
   ([`22-calidad-de-datos.md`](22-calidad-de-datos.md) §7.3). **Nadie honesto lo ve nunca.**
3. La alternativa —ordenar por `answers_count × trust_score`— sí violaría RF-207: cualquiera que vea
   su puntaje y sepa su cantidad de respuestas **despeja su trust dividiendo**.

Se descartó también el filtro duro sin el de marcados, y el orden por "respuestas que entraron al
último export": este último congela la tabla entre corridas de agregación y la vuelve incomprensible.

### 5.3 Las ventanas

`answers_count` es un contador total y sólo sirve para `window=all`. Las ventanas de día y semana se
cuentan sobre `responses`:

```sql
SELECT respondent_id, count(*) AS n
FROM responses
WHERE created_at > now() - interval '7 days'
GROUP BY respondent_id
ORDER BY n DESC
LIMIT 50;
```

Con el volumen del piloto —a lo sumo unos miles de filas— es una consulta trivial, sostenida por el
índice `responses_recent`. El resultado se cachea **60 segundos** en el proceso: una tabla de
posiciones que se actualiza cada minuto es indistinguible de una en vivo para quien la mira, y saca
la consulta del camino de cada petición.

Las ventanas no son sólo una comodidad: son lo que hace que la tabla **no esté decidida**. Con una
sola ventana total, después de dos semanas el top 10 es inalcanzable y la mecánica deja de motivar a
todos menos a diez personas. `day` y `week` le dan a cualquiera una carrera que puede ganar hoy.

---

## 6. Anti-gaming

| Vector | Qué lo contiene |
|---|---|
| Responder al azar a toda velocidad | Límite de 40/min; detección de apuradas y *straightlining*; el trust bajo saca de la tabla (§5.1) |
| Fabricar identidades para inflar la posición | Marcado por huella duplicada, que además excluye de la tabla (RF-208) |
| Optimizar el trust score | Imposible: no se expone, y no hay ninguna señal de qué respuesta lo movió (RF-207) |
| Coordinar respuestas para mover un campeón | El trust pondera, el decaimiento por recencia diluye, y `D_unknown_rate` más la entropía dejan rastro en el Informe de Calidad de Datos |
| Elegir un alias ofensivo | No se puede elegir (§4) |

El vector que **no** está cubierto es una campaña coordinada de muchas personas reales con
identidades legítimas votando en la misma dirección. No hay defensa técnica contra eso en un sistema
anónimo y abierto; lo que hay es visibilidad: un pico de volumen sobre un campeón puntual aparece en
el panel, y la distribución de respuestas por parche queda en el crudo para siempre.

---

## 7. Parámetros

Todos en `app_settings` (RF-606):

| Clave | Valor inicial | Qué controla |
|---|---|---|
| `gamification.streak_gap_minutes` | `30` | Pausa que corta `current_streak` |
| `gamification.day_streak_min_answers` | `5` | Respuestas diarias para sostener la racha de días |
| `gamification.streak_timezone` | `America/Argentina/Buenos_Aires` | Dónde empieza el día |
| `gamification.leaderboard_size` | `50` | Filas de la tabla |
| `gamification.leaderboard_cache_seconds` | `60` | Vida del caché de las ventanas |
| `export.min_trust` | `0.30` | Umbral compartido con el filtro de exportación (§5.1) |

`export.min_trust` es **la misma clave** que usa el pipeline de agregación, no una copia. Que la
tabla de posiciones y el export usen literalmente el mismo umbral es lo que hace verdadera la frase
"la tabla muestra a quien contribuyó al conjunto de datos"; con dos parámetros independientes, uno se
desincronizaría del otro en la primera calibración.

---

## 8. Verificación

| Qué se prueba | Cómo | CA |
|---|---|---|
| La racha corta con la pausa | Dos respuestas separadas por 31 minutos dejan `current_streak = 1` | CA-310 |
| `best_streak` no baja | Cortar una racha de 12 conserva `best_streak = 12` | CA-310 |
| La racha de días suma una vez por día | 20 respuestas en un día suman 1 a `current_day_streak`, no 4 | CA-311 |
| La racha de días se corta | Saltear un día calendario reinicia `current_day_streak` en 1 | CA-311 |
| El alias no es un identificador | El alias no se puede derivar del `respondent_id` ni de la huella | CA-312 |
| Los marcados no aparecen | Un respondedor con `is_flagged` no está en el top 50 aunque tenga el mayor volumen | CA-313 |
| Los de trust bajo no aparecen | Un respondedor con `trust_score = 0.20` no está en la tabla | CA-313 |
| El trust no se filtra | Ninguna respuesta de `/leaderboard` ni de `/me` permite despejar el trust | CA-303 |

---

Ver el índice en [`README.md`](README.md) y las decisiones cerradas en [`13-adr/`](13-adr/).
