# 36 — Manual de uso de la app de administración

> Estado: **borrador** · Última revisión: 13/11/2026

Este manual es para **quien opera el panel** durante el piloto: qué mirar, qué tocar y qué no. No
reemplaza a [`24-panel-admin.md`](24-panel-admin.md), que es la especificación (el contrato); acá
sólo está lo necesario para usarlo. Si algo de este manual contradice al 24, manda el 24.

Cómo leerlo:

- Para **arrancar**, alcanza con §1 a §4 (unos minutos).
- Para **cambiar un parámetro**, §5 dice en una línea para qué sirve cada uno y cuándo se toca.
- §6 es la referencia: qué hace cada parámetro en detalle y qué pasa si se sube o se baja. Se lee
  la entrada que hace falta, no de corrido.

---

## 1. Abrirla

La app corre **sólo en el servidor del laboratorio** y sólo se abre desde esa misma máquina. No
tiene usuario ni clave: quien llega a la pantalla ya está sentado en el servidor
([ADR-025](13-adr/ADR-025-app-de-administracion-local.md)).

1. La primera vez, instalar el backend y crear `admin/.env` desde `admin/.env.example` (los pasos
   están en el [`README.md`](../README.md) del repositorio). El `.env` tiene la contraseña de la
   base: **nunca se copia a otro lado**.
2. En una terminal, desde la carpeta `admin/`: `.\run.ps1` en Windows o `./run.sh` en Linux.
3. Abrir **`http://127.0.0.1:5000`** en el navegador del servidor.

Si se cierra la terminal, la app se apaga. Todo lo que se hizo queda guardado en la base, salvo un
job o una exportación que estuviera corriendo en ese momento: ésos se cortan y hay que volver a
lanzarlos.

## 2. La pantalla

A la izquierda, el menú con las diez vistas. Arriba, en todas, una franja con el **parche vigente**
(si dice «Sin parche vigente» en rojo, el sitio público no puede servir preguntas: ver §3.2) y la
hora de los datos que se están viendo. **Las vistas no se refrescan solas**: el botón *Actualizar*
de la franja vuelve a leer la base.

| Vista | Para qué sirve, en una línea |
|---|---|
| **Resumen** | ¿Está entrando gente? Respuestas, respondedores, envíos de hoy y el gráfico por día |
| **Conectividad y tier** | ¿Los datos alcanzan para ordenar campeones? Y si ya se puede habilitar el tier 2 |
| **Cobertura** | Qué campeones y dimensiones tienen pocas respuestas (rojo = menos de 10) |
| **Calidad** | Cómo se reparte la confianza de los respondedores, y quiénes están marcados |
| **Pool** | Qué campeones entran en cada tier, y moverlos de tier |
| **Parámetros** | Los valores que gobiernan el sistema (§4 a §6) |
| **Jobs** | Los cuatro procesos de mantenimiento, con un botón *Ejecutar* cada uno |
| **Parches y seeds** | Cargar un parche nuevo y activarlo, en cuatro pasos numerados |
| **Exportaciones** | Generar los seis CSV y el Informe de Calidad de Datos, y descargarlos |
| **Auditoría** | El registro de todo lo que se cambió desde el panel, del más nuevo al más viejo |

Las vistas de mirar (Resumen, Conectividad, Cobertura, Calidad, Auditoría) **no cambian nada**: se
pueden abrir sin miedo. Toda acción que escribe pide confirmación y queda en la Auditoría.

## 3. Qué hacer y cuándo

### 3.1 Durante el piloto, regularmente

1. **Jobs → Ejecutar** los cuatro. Todavía no corren solos (eso llega con el despliegue), así que
   alguien tiene que lanzarlos. La frecuencia prevista en [`21-sampler.md`](21-sampler.md) §9 es:

   | Job | Cada cuánto | Qué hace |
   |---|---|---|
   | `refresh_question_stats` | 15 min | Recalcula las estadísticas de cada pregunta y retira las honeypots que la gente falla demasiado |
   | `check_graph_connectivity` | 1 h | Busca dimensiones partidas y marca las preguntas «puente» que las unen |
   | `detect_degenerate_patterns` | diaria | Busca respuestas apuradas y gente que toca siempre el mismo lado |
   | `flag_duplicate_fingerprints` | diaria | Marca a quien fabrica identidades borrando cookies |

   Un job tarda segundos. Mientras corre, su botón queda deshabilitado; los cuatro pueden correr a
   la vez.
2. **Resumen**: que el volumen no se caiga.
3. **Calidad**: que la distribución del trust no se corra hacia la izquierda de la línea vertical
   (`export.min_trust`), y revisar la lista de marcados.
4. **Conectividad y tier**: cuántas dimensiones están conectadas.

### 3.2 Con cada parche nuevo de League of Legends

**Parches y seeds**, los cuatro pasos en orden:

1. **Catálogo de campeones**: la versión del parche. Si Data Dragon no responde, tildar el respaldo.
2. **Snapshot de pick rate**: elegir el `pick_rate_*.csv` de la lista y completar la URL y la fecha
   de la captura.
3. **Honeypots**: elegir el `honeypots_*.yaml` de la lista.
4. **Activar**: sin *forzar*. Si falta algo, el panel lo lista y no activa; se completa lo que falta
   y se vuelve a intentar.

Los archivos tienen que estar **antes** en `infra/seeds/` del servidor: el panel no sube archivos.

### 3.3 Para generar la entrega

**Exportaciones → Generar CSV**. El formulario viene con los valores de *Parámetros*; lo normal es no
tocarlo. Cuando termina, cada CSV y el Informe se descargan desde la lista de corridas. Una sola
exportación a la vez.

### 3.4 Un falso positivo de la huella

Si en una sala de la facultad (mismas máquinas, misma red) varias personas quedaron marcadas
juntas: **Calidad → Marcar o desmarcar a mano**, con el id completo del respondedor y un motivo,
que queda en la auditoría. Ver también `quality.fingerprint_max_identities` en §6.2.

## 4. Cambiar un parámetro

1. **Parámetros → Editar** en la clave.
2. Escribir el valor nuevo en el recuadro. Es JSON: un número va tal cual (`0.25`, con punto), un
   texto entre comillas (`"America/Argentina/Buenos_Aires"`), una lista entre corchetes (`[10, 15]`).
3. **Revisar cambio** muestra el actual y el nuevo lado a lado. **Guardar** lo aplica.

Cinco reglas que conviene saber antes:

- **El valor nuevo tiene que tener la misma forma que el actual.** Si era un número, un número; si
  era una lista de dos números, una lista de dos números; si era un objeto con cuatro claves, las
  mismas cuatro. Si no, el panel lo rechaza y no guarda nada. Es a propósito: un texto en lugar de
  un número llegó a dejar el sitio sin preguntas para todos.
- **No hay más validación que ésa.** El panel no sabe si `0.85` tiene sentido para una clave: eso
  queda en manos de quien edita. Por eso existe §5.
- **El sitio público tarda hasta 60 segundos** en ver el cambio.
- **No se pueden crear claves** desde el panel, sólo editar las que hay.
- **Todo cambio queda en la Auditoría** con el valor anterior. Deshacer es editar de nuevo y poner
  el anterior.

## 5. Los parámetros de un vistazo

La columna *Cuándo se cambia* resume lo que dicen los documentos de diseño:

- **Plan**: hay una regla o un cronograma escrito para cambiarlo.
- **Calibrar**: el valor inicial es una primera estimación, a ajustar con los datos del piloto
  antes de la entrega final.
- **Dejar**: no hay ningún motivo documentado para cambiarlo. Si parece que hace falta, primero
  preguntar.

### `sampler.` — qué preguntas se le muestran a la gente

| Clave | Para qué sirve | Inicial | Cuándo se cambia |
|---|---|---|---|
| `enabled_pool_tiers` | Cuántos campeones entran en las preguntas: sólo los del tier 1, o también los del 2… | `1` | **Plan**: sólo cuando *Conectividad* dice que se cumple la condición |
| `epsilon` | Qué proporción de preguntas se elige al azar en vez de por necesidad | `1.00` | **Plan**: 1.00 → 0.30 → 0.20 |
| `weights` | Qué importa más al elegir la próxima pregunta | ver §6.1 | Dejar |
| `cold_threshold` | Cuántas respuestas necesita una pregunta para dejar de ser «nueva» | `5` | Dejar |
| `consensus_threshold` | Cuántas respuestas necesita una pregunta para mostrar «qué contestó la mayoría» | `20` | Dejar |
| `candidate_limit` | Cuántas preguntas candidatas se consideran cada vez | `50` | Dejar |
| `max_rejection_retries` | Cuántas veces se vuelve a sortear antes de rendirse | `10` | Dejar |

### `quality.` — detectar respuestas poco confiables

| Clave | Para qué sirve | Inicial | Cuándo se cambia |
|---|---|---|---|
| `honeypot_every` | Cada cuántas preguntas aparece una pregunta trampa | `[10, 15]` | Dejar |
| `honeypot_min_pass_rate` | Si menos de esta proporción la acierta, la trampa está mal y se retira | `0.85` | Dejar |
| `honeypot_min_attempts` | Cuántos intentos hacen falta antes de juzgar una trampa | `40` | Dejar |
| `retest_every` | Cada cuántas preguntas se repite una ya contestada | `30` | Dejar |
| `retest_min_distance` | Cuántas preguntas tienen que haber pasado desde la original | `15` | Dejar |
| `fast_answer_ms` | Por debajo de este tiempo una respuesta cuenta como apurada | `800` | Dejar |
| `straightline_run` | Cuántas respuestas seguidas del mismo lado son sospechosas | `8` | Dejar |
| `fingerprint_max_identities` | Cuántas identidades por dispositivo en 24 h antes de marcar | `5` | **Plan**: subir durante una jornada presencial y volver a bajar |
| `trust_weights` | Cuánto pesa cada señal en la confianza de un respondedor | ver §6.2 | Dejar |
| `trust_smoothing` | Cuánto se tarda en juzgar a alguien nuevo | `2` | Dejar |
| `ip_rate_per_minute` | Respuestas por minuto que se aceptan de una misma red | `40` | **Plan**: subir antes de difundir el piloto en un aula |
| `ip_rate_per_day` | Respuestas por día que se aceptan de una misma red | `1500` | **Plan**: ídem |

### `export.` — el umbral de confianza

| Clave | Para qué sirve | Inicial | Cuándo se cambia |
|---|---|---|---|
| `min_trust` | Quién cuenta: debajo de esta confianza, las respuestas no entran al CSV y la persona no aparece en la tabla de posiciones | `0.30` | **Calibrar** |

### `gamification.` — rachas y tabla de posiciones

| Clave | Para qué sirve | Inicial | Cuándo se cambia |
|---|---|---|---|
| `streak_gap_minutes` | Cuántos minutos de pausa cortan la racha de respuestas | `30` | Dejar |
| `day_streak_min_answers` | Cuántas respuestas en un día sostienen la racha de días | `5` | Dejar |
| `streak_timezone` | En qué zona horaria empieza el día | `America/Argentina/Buenos_Aires` | **Plan**: sólo si el piloto se difunde fuera del país |
| `leaderboard_size` | Cuántas filas tiene la tabla de posiciones | `50` | Dejar |
| `leaderboard_cache_seconds` | Cada cuánto se recalcula la tabla del día y la semana | `60` | Dejar |

### `aggregation.` — cómo se calculan los CSV

Sólo se usan al **generar una exportación**: cambiarlos no afecta al sitio público.

| Clave | Para qué sirve | Inicial | Cuándo se cambia |
|---|---|---|---|
| `decay_halflife_days` | Cada cuántos días una respuesta pierde la mitad de su peso | `21` | **Calibrar** |
| `bootstrap_samples` | Cuántas veces se recalcula todo para estimar los intervalos de confianza | `2000` | **Calibrar** |
| `power_sigma` | Qué tan ancha es la curva de poder de un campeón alrededor de su pico | `7.5` | **Calibrar** |
| `bt_prior` | Un pequeño empuje para que el cálculo no explote con campeones invictos | `0.5` | **Calibrar** |
| `support_thresholds` | Cuántas respuestas y qué precisión hacen falta para llamar a un dato `solid` o `limited` | ver §6.5 | **Calibrar** |
| `duo_lambda_champion` | Cuánto se frena el aporte individual de cada campeón en las duplas | `0.10` | Dejar |
| `duo_lambda_interaction` | Cuánto se frena lo específico de cada dupla | `1.00` | Dejar |
| `max_iter` | Cuántos pasos puede dar el ajuste como máximo | `500` | Dejar |
| `tol` | Cuándo el ajuste se da por terminado | `1e-9` | Dejar |
| `segment_min_respondents` | Mínimo de personas para reportar un segmento de rango | `15` | Dejar |
| `segment_min_comparisons` | Mínimo de comparaciones para reportar un segmento de rango | `300` | Dejar |

---

## 6. Los parámetros en detalle

Cada entrada dice qué hace, qué pasa si se sube o se baja, y dónde está la definición completa.

### 6.1 `sampler.` — [`21-sampler.md`](21-sampler.md)

Cada vez que alguien pide una pregunta, el *sampler* decide cuál. En orden: si toca una honeypot o
un retest, va eso; si hay una pregunta «puente» que esa persona no contestó, va ésa; si no, tira una
moneda cargada con `epsilon` y o bien **explora** (una combinación al azar) o bien **explota**
(la pregunta más necesaria según una fórmula de prioridad).

**`sampler.enabled_pool_tiers`** — Los campeones están repartidos en tiers por pick rate
([ADR-006](13-adr/ADR-006-pool-escalonado-por-pick-rate.md)). Con `1`, las preguntas sólo usan los
58 del tier 1; con `2`, también los del tier 2. Más campeones con la misma gente **diluye** la
muestra: cada campeón recibe menos respuestas. Por eso hay una regla (21 §7.2): se pasa a `2` sólo
cuando la **mediana de `D_n` del tier 1 llega a 25 y al menos 6 de las 8 dimensiones están
conectadas**. La vista *Conectividad y tier* calcula las dos cosas y dice en una línea si se cumple.
Con el volumen esperado del piloto es probable que no se cumpla nunca, y está bien. Al cambiarlo, la
auditoría lo registra como `set_enabled_tiers`.

**`sampler.epsilon`** — La probabilidad de explorar. Con `1.00` todas las preguntas son al azar,
que es lo correcto al principio porque no hay datos para decidir qué falta
([ADR-012](13-adr/ADR-012-sampler-uniforme-en-arranque-en-frio.md)). El cronograma previsto
(21 §4.3): `1.00` en el lanzamiento cerrado (semana 7), `0.30` en el público (semana 8), `0.20` de
la semana 9 en adelante. Más alto: más combinaciones nuevas, cobertura más pareja, intervalos que
se angostan más despacio. Más bajo: se insiste en lo que falta, pero el sistema puede encerrarse en
pocas preguntas. Señal de que está bajo: los intervalos se angostan pero la cobertura no avanza.
Señal de que está alto: la cobertura avanza pero los intervalos no se angostan.

**`sampler.weights`** — Un objeto con cuatro pesos, `{"escasez": 0.35, "informacion": 0.25,
"cobertura": 0.20, "puente": 1.00}`, que forman la prioridad de una pregunta en la rama de
explotación (21 §3):

- `escasez`: preferir lo que menos se preguntó.
- `informacion`: insistir donde la comunidad está dividida.
- `cobertura`: atender al campeón peor cubierto.
- `puente`: unir partes desconectadas del grafo.

`puente` vale 1.00 **a propósito**: como los otros tres suman a lo sumo 0.80, una pregunta puente
gana siempre. Bajarlo a menos de 0.80 rompe esa garantía
([ADR-008](13-adr/ADR-008-conectividad-por-componentes.md)).

**`sampler.cold_threshold`** — Una pregunta con menos de 5 respuestas está en el estrato «frío» y
sólo se elige por exploración; desde 5 entra a competir por prioridad (ADR-012). La razón: con menos
datos, la entropía y la cobertura de esa pregunta son ruido. Más alto: más tiempo en modo azar; más
bajo: decisiones tomadas sobre muy pocas respuestas.

**`sampler.consensus_threshold`** — Después de responder, la persona ve qué contestó la mayoría,
pero sólo si la pregunta tiene al menos 20 respuestas; antes ve «you're one of the first to answer
this». Bajarlo muestra «consensos» de tres o cuatro personas, que no lo son.

**`sampler.candidate_limit`** — En la rama de explotación, cuántas de las preguntas con más
prioridad se traen para buscar una que la persona no haya contestado. Si las 50 ya las contestó,
se le sirve un retest como último recurso. Es un tope de rendimiento, no un criterio estadístico.

**`sampler.max_rejection_retries`** — En la rama de exploración, cuántos sorteos se intentan hasta
dar con una pregunta que la persona no contestó; también cuántas veces se re-sortean los tres
campeones extra del ranking de cinco cuando alguno forma una honeypot. Es un tope de rendimiento,
no un criterio estadístico.

### 6.2 `quality.` — [`22-calidad-de-datos.md`](22-calidad-de-datos.md)

Ninguna respuesta se borra nunca. Lo que hace este bloque es calcular un **trust score** entre 0 y 1
por respondedor, que después decide cuánto pesan sus respuestas y si entran al CSV. Se arma con
cuatro señales: honeypots, retests, patrones degenerados y huella duplicada.

**`quality.honeypot_every`** — Una lista `[mín, máx]`. Cada tantas preguntas, sorteado dentro de
esa ventana, aparece una **honeypot**: una pregunta con respuesta objetivamente verificable, que
sólo falla quien no sabe o no está leyendo. Se sortea para que nadie pueda contar y adivinar cuál
es. La cuenta es por persona, no por sesión. Más seguido: se detecta antes a quien contesta mal,
pero el catálogo de honeypots del parche se gasta más rápido y la gente las nota.

**`quality.honeypot_min_pass_rate`** — Si menos del 85 % de la gente acierta una honeypot, la
honeypot se retira sola: lo más probable es que la honeypot esté mal (un parche cambió al campeón),
no que el 15 % sea descuidado. Al retirarla se recalcula la confianza de todos los que la habían
recibido. Más alto: se retiran honeypots buenas. Más bajo: honeypots malas siguen castigando gente.

**`quality.honeypot_min_attempts`** — La regla de arriba no se aplica hasta que la honeypot tiene
40 intentos (sin contar «no sé» ni respondedores marcados). Sin este piso, la primera persona que
fallara una honeypot la retiraría, y unas pocas identidades falsas podrían vaciar el catálogo.

**`quality.retest_every`** — Cada 30 preguntas se repite una que la misma persona ya contestó. Si
contesta lo mismo (o algo cercano, según el tipo), es consistente; si no, probablemente contesta al
azar.

**`quality.retest_min_distance`** — La pregunta repetida tiene que haberse contestado hace al menos
15 preguntas, para que no la reconozca de memoria inmediata. La debilita, no la elimina.

**`quality.fast_answer_ms`** — Una respuesta en menos de 800 ms cuenta como apurada: el enunciado
más corto del sistema no se lee y se decide en menos que eso. Una sola no significa nada; lo que
entra a la confianza es la **proporción** de respuestas apuradas. Lo aplica el job
`detect_degenerate_patterns`.

**`quality.straightline_run`** — Ocho respuestas seguidas en la misma posición de pantalla (siempre
la izquierda, por ejemplo) cuentan como una racha sospechosa. Por azar pasa menos del 1 % de las
veces. Más bajo: se marca a gente que tuvo una racha legítima. Lo aplica el mismo job.

**`quality.fingerprint_max_identities`** — Si un mismo dispositivo genera más de 5 identidades en 24
horas, se marcan **todas** (no se puede saber cuál era la original). Tiene un falso positivo
conocido y aceptado: **una sala con computadoras idénticas** produce la misma huella para todas. La
regla escrita (22 §6.3) es: si se sabe que va a haber una jornada presencial, **subirlo para esa
ventana y volver a bajarlo después**. Ambos cambios quedan en la auditoría. Lo aplica el job
`flag_duplicate_fingerprints`.

**`quality.trust_weights`** — Un objeto `{"honeypot": 0.60, "retest": 0.40, "degenerate": 0.50}`.
La confianza es

```
trust = (0.60 · honeypots + 0.40 · retests) · (1 − 0.50 · patrones degenerados)
```

`honeypot` y `retest` reparten la nota base y deberían sumar 1 para que la confianza llegue hasta 1.
`degenerate` es cuánto descuenta, como máximo, ir apurado o tocar siempre el mismo lado: con 0.50,
la mitad. Cambiarlos mueve a todos respecto de `export.min_trust`.

**`quality.trust_smoothing`** — Cuánto «beneficio de la duda» tiene alguien nuevo. Con 2, una
persona sin datos arranca en 0.500 y fallar su primera honeypot la baja a 0.400, no a 0.200. Más
alto: hacen falta más observaciones para mover a alguien. Más bajo: se juzga con muy pocos datos.

**`quality.ip_rate_per_minute`** y **`quality.ip_rate_per_day`** — Topes de respuestas que el sitio
acepta desde una misma red, sumando a todas las personas detrás de ella
([ADR-033](13-adr/ADR-033-limite-por-hash-de-ip-con-sal.md)). Frenan a un script que crea
identidades sin parar. Su costo: un aula o el wifi de la facultad salen por una sola IP y
comparten el tope; con 40 por minuto y unas 10 respuestas por minuto por persona, **cuatro personas
a la vez ya lo alcanzan**. La regla escrita: **antes de difundir el piloto en un aula, subirlos desde
el panel**. Cuánto, depende de cuánta gente comparta la red; no está fijado en ningún documento.

### 6.3 `export.` — [`22-calidad-de-datos.md`](22-calidad-de-datos.md) §7.3

**`export.min_trust`** — Una sola clave con **dos usos**, a propósito
([ADR-014](13-adr/ADR-014-leaderboard-filtra-por-confianza.md)):

1. Las respuestas de alguien con confianza menor no entran a la exportación.
2. Esa persona tampoco aparece en la tabla de posiciones pública.

Con la fórmula actual, bajar de 0.30 exige fallar unas cinco honeypots: no es un accidente. Más
alto: datos más limpios y menos muestra. Más bajo: más muestra y más ruido. En *Calidad*, la línea
vertical del histograma marca dónde está.

Ojo: el formulario de *Exportaciones* trae este valor precargado, y **cambiarlo ahí afecta sólo a
esa corrida**, no a la tabla de posiciones. Cambiarlo en *Parámetros* cambia las dos cosas. El valor
va entre 0 y 1, sin incluir el 0.

### 6.4 `gamification.` — [`23-gamificacion.md`](23-gamificacion.md)

**`gamification.streak_gap_minutes`** — La racha de respuestas seguidas se corta si pasan más de 30
minutos entre dos respuestas. Lo bastante largo para que atender el timbre no la corte, lo bastante
corto para que «seguidas» signifique algo.

**`gamification.day_streak_min_answers`** — Un día cuenta para la racha de días si la persona
respondió al menos 5 veces. Más alto: la racha cuesta más y premia más el compromiso; más bajo: se
sostiene con casi nada.

**`gamification.streak_timezone`** — Dónde empieza el día para la racha de días y para el gráfico
de *Resumen*. Es un nombre de zona como `"America/Argentina/Buenos_Aires"`, entre comillas. En UTC,
responder a las 22:00 de Argentina sumaría al día siguiente.

**`gamification.leaderboard_size`** — Cuántas filas tiene la tabla de posiciones.

**`gamification.leaderboard_cache_seconds`** — La tabla del día y la de la semana se recalculan a lo
sumo cada 60 segundos. Más bajo: más carga sobre la base para un dato que nadie mira al segundo.

### 6.5 `aggregation.` — [`25-agregacion.md`](25-agregacion.md)

Estos parámetros se leen al **generar una exportación** y quedan guardados con ella, así que
cualquier corrida se puede reproducir. Los primeros cuatro y los umbrales se calibran con los datos
del piloto antes de la entrega final.

**`aggregation.decay_halflife_days`** — Cada respuesta pesa `trust × 0.5^(días / 21)`: a los 21
días pesa la mitad, a los 42 un cuarto. Como los parches salen cada dos semanas y una exportación
típica toma tres, la respuesta más vieja sigue aportando un cuarto. Más corto: se desperdicia
muestra. Más largo: se mezclan campeones que ya cambiaron con un parche. Se puede cambiar sólo para
una corrida desde el formulario de *Exportaciones*. Tiene que ser mayor que 0.

**`aggregation.bootstrap_samples`** — Los intervalos de confianza se calculan recalculando todo
2000 veces sobre remuestreos de los datos. Más remuestreos: intervalos más estables y una
exportación más lenta (usa todos los procesadores del servidor). Menos: más rápido y más ruidoso.
También se puede cambiar sólo para una corrida.

**`aggregation.power_sigma`** — El CSV `peak_timing` da el minuto de pico de cada campeón y una
curva de poder alrededor de él (minutos 5, 10, 15, 20 y 25). `σ` es el ancho de esa curva, en
minutos ([ADR-009](13-adr/ADR-009-curva-de-poder-gaussiana.md)). Más alto: curvas más planas, el
campeón «sirve» en más momentos de la partida. Más bajo: curvas más puntiagudas.

**`aggregation.bt_prior`** — En Bradley-Terry, un campeón que ganó todas sus comparaciones tendría
un score infinito. Este valor le suma a cada uno media victoria y media derrota contra un rival
promedio, y así acerca a 0 a quien tiene poquísimos datos. Más alto: más encogimiento hacia el
promedio.

**`aggregation.support_thresholds`** — Cada valor del CSV lleva una etiqueta `solid`, `limited` o
`insufficient` ([ADR-011](13-adr/ADR-011-support-level-en-vez-de-excluir.md)). Para cada tipo de
magnitud hay dos niveles, y cada nivel exige **las dos condiciones**: al menos `n` respuestas y un
intervalo de confianza no más ancho que `width`. Lo que no llega a `limited` es `insufficient`. Los
valores son los de [`26-esquema-de-salida.md`](26-esquema-de-salida.md) §2.4:

| Magnitud | `solid` | `limited` |
|---|---|---|
| `dimension` | n ≥ 25, ancho ≤ 0.60 | n ≥ 10, ancho ≤ 1.20 |
| `peak_minute` | n ≥ 20, ancho ≤ 4 | n ≥ 10, ancho ≤ 8 |
| `lane_strength` | n ≥ 20, ancho ≤ 0.60 | n ≥ 8, ancho ≤ 1.20 |
| `synergy` | n ≥ 15, ancho ≤ 0.80 | n ≥ 6, ancho ≤ 1.50 |
| `trait` | n ≥ 20, ancho ≤ 0.25 | n ≥ 10, ancho ≤ 0.45 |

Se edita como un objeto anidado: hay que conservar las cinco magnitudes, los dos niveles y las
claves `n` y `width` de cada uno. Subir los números hace más exigente la etiqueta `solid`; no
cambia ningún valor del CSV, sólo cómo se rotula.

**`aggregation.duo_lambda_champion`** y **`aggregation.duo_lambda_interaction`** — En
`duo_features`, la fuerza de una dupla es «lo que aporta A + lo que aporta B + lo propio de la
dupla A-B». Los dos λ frenan esos términos para que no se disparen con pocos datos; el de la
interacción es mucho más fuerte a propósito, así que una dupla con pocas respuestas queda cerca de
la suma de sus integrantes. Subir `duo_lambda_interaction` hace las duplas todavía más «aditivas»;
bajarlo deja que pocas respuestas muevan mucho a una dupla.

**`aggregation.max_iter`** y **`aggregation.tol`** — El ajuste es iterativo: se detiene cuando el
cambio entre dos pasos es menor que `tol` o cuando llega a `max_iter` pasos. Son controles
numéricos del ajuste, no criterios estadísticos.

**`aggregation.segment_min_respondents`** y **`aggregation.segment_min_comparisons`** — El Informe
de Calidad compara los resultados entre segmentos de rango declarado (bajo, medio, alto, sin rango,
no declarado). Un segmento con menos de 15 personas o 300 comparaciones en una dimensión se reporta
como «no calculable» con su `n`, en vez de con un número frágil (25 §3.5).

---

## 7. Cuando algo sale mal

| Lo que se ve | Qué significa | Qué hacer |
|---|---|---|
| «No se pudo leer la base» | El panel no llega a Postgres | Revisar `admin/.env` y que la base esté arriba |
| La página no carga desde otra computadora | Es lo esperado: sólo atiende en el servidor | Abrirla en el servidor |
| `invalid_parameter` al guardar un parámetro | El valor no tiene la forma del actual (§4) | Copiar el actual y cambiar sólo el número |
| «No es JSON válido» | Falta una comilla, sobra una coma, o se usó coma decimal | `0.25`, no `0,25`; los textos entre comillas dobles |
| `job_running` / `export_running` | Ya hay uno corriendo | Esperar a que termine |
| `patch_not_ready` al activar | Falta el snapshot o las honeypots del parche | Hacer el paso que falta (§3.2). Forzar sólo si se sabe por qué |
| `seed_invalid` | El archivo de `infra/seeds/` tiene errores | Corregir el archivo; el panel lista cada problema |
| Un job o una exportación quedó en error tras reiniciar | El proceso se reinició y la corrida se perdió | Volver a lanzarla |
| Una exportación falla porque ninguna respuesta pasa los filtros | Nada entra a la corrida (por ejemplo, `min_trust` muy alto o una ventana sin respuestas) | Revisar el umbral y la ventana de parches |

---

Ver el índice en [`README.md`](README.md). La especificación del panel es
[`24-panel-admin.md`](24-panel-admin.md).
