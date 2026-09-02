# 22 — Calidad de datos y trust score

> Estado: **v1** · Última revisión: 01/09/2026 · Ola 3 · Desbloquea la semana 5 del cronograma

Cómo el sistema distingue una respuesta pensada de una apurada, de una al azar o de una fabricada, y
qué hace con esa distinción. Es el módulo que hace que un etiquetado abierto y anónimo pueda
defenderse como instrumento de medición.

Requerimientos que implementa: RF-201 a RF-209.

---

## 1. El principio: nada se borra, todo es peso

`responses` es append-only ([ADR-002](13-adr/ADR-002-responses-append-only.md)). Ninguna señal de
calidad borra, corrige ni oculta una respuesta. **Todo el módulo actúa sobre dos cosas y nada más:**

1. el `trust_score` del respondedor, que pondera sus respuestas en la agregación y las filtra en la
   exportación;
2. la marca `is_flagged`, que lo excluye de la agregación y de la tabla de posiciones.

Esto no es purismo. Es lo que permite **reanalizar**: si dentro de tres meses el laboratorio quiere
la corrida con `min_trust = 0.10` en vez de `0.30`, los datos están. Si se hubieran borrado, no.

---

## 2. Las cuatro señales

| Señal | Qué detecta | Cuándo se mide |
|---|---|---|
| **Honeypot** | No sabe de LoL, o no está leyendo | En el `INSERT`, sincrónico |
| **Test-retest** | Contesta al azar: no es consistente consigo mismo | En el `INSERT`, sincrónico |
| **Patrones degenerados** | Va demasiado rápido, o siempre toca el mismo lado | Job diario |
| **Huella duplicada** | Fabrica identidades borrando cookies | Job diario |

Las dos primeras miden a la persona respondiendo. Las dos últimas miden el comportamiento agregado.
Ninguna es concluyente sola; el `trust_score` las combina.

---

## 3. Honeypots — RF-201, RF-202

### 3.1 Qué es exactamente una honeypot

Una pregunta cuya respuesta el sistema ya conoce, intercalada entre las reales y **visualmente
idéntica** a ellas. `is_honeypot` y `expected_answer` nunca salen de la base: cualquier señal en el
cliente —una clase CSS distinta, un campo de más en el JSON, hasta un tiempo de respuesta
diferente— invalidaría el mecanismo entero.

El punto conceptual, que decide todo lo demás: **una honeypot no mide la verdad, mide si la persona
está leyendo y sabe de qué se le habla.** La respuesta esperada tiene que ser tan obvia que fallarla
sólo se explique por desatención o desconocimiento, nunca por una diferencia legítima de opinión.

Una honeypot discutible no mide calidad: **castiga disidencia**, y sesga el conjunto de datos hacia
el consenso — que es exactamente lo que este proyecto no quiere producir.

### 3.2 De dónde sale el catálogo: el kit del campeón

Las honeypots se redactan a partir de **hechos verificables en el kit del campeón**, no de juicio
experto. Ese es el criterio completo, y la razón es que hace que la respuesta esperada sea
defendible sin apelar a la autoridad de quien la escribió: la justificación es la descripción de una
habilidad, no una opinión.

Sólo seis de las ocho dimensiones admiten este tratamiento:

| Dimensión | Qué hecho del kit la resuelve | Ejemplo del par |
|---|---|---|
| `mobility` | Uno tiene dash, salto o parpadeo; el otro no tiene ninguna habilidad de desplazamiento | Yasuo > Malphite |
| `cc` | Uno tiene dos o más habilidades de control duro (aturdir, enraizar, elevar); el otro ninguna | Leona > Master Yi |
| `poke` | Uno es a distancia con una habilidad de daño de rango largo; el otro es cuerpo a cuerpo sin daño a distancia | Ziggs > Udyr |
| `waveclear` | Uno tiene daño en área que limpia una oleada; el otro sólo tiene daño de objetivo único | Ziggs > Yi |
| `engage` | Uno tiene acercamiento + control con el que iniciar; el otro no tiene forma de iniciar | Alistar > Jhin |
| `peel` | Uno tiene una habilidad que apunta a un aliado (escudo, curación, velocidad); el otro no tiene ninguna | Lulu > Katarina |

`scaling` y `pick` **no tienen honeypots**, y no es una omisión: no hay un hecho del kit que las
resuelva sin discusión. El escalado es una propiedad de la curva de poder, no de una habilidad, y
el potencial de pick depende de la composición y del parche.

Que falten dos dimensiones no debilita nada: **la honeypot mide al respondedor, no a la dimensión.**
Que alguien conteste con atención no depende de qué dimensión se le preguntó.

Por la misma razón, **todas las honeypots son de tipo 1**:

| Tipo | Por qué no lleva honeypots |
|---|---|
| 2 — pico de poder | Un slider no tiene respuesta incorrecta, sólo una distribución |
| 3 — matchup | Depende del parche y de la habilidad relativa; es opinión legítima |
| 4 — sinergia | Idem, y con menos consenso todavía |
| 5 — atributos | Es una proporción por definición: marcar de más o de menos no es un error |

El tipo 1 es además el 50 % de la sesión, así que una honeypot nunca se ve fuera de lugar por
frecuencia — otra forma en la que podría delatarse.

### 3.3 El catálogo como dato versionado

~40 pares por parche, en `infra/seeds/honeypots_<patch>.yaml`, cargados como filas de `questions`
con `is_honeypot = true` y `expected_answer`:

```yaml
- champion_a: Yasuo
  champion_b: Malphite
  dimension: mobility
  expected: {choice: "a"}
  rationale: >
    Yasuo tiene Barrido del Acero (E), un dash sin cooldown sobre subditos.
    Malphite no tiene ninguna habilidad de desplazamiento salvo su ultimate,
    que es un inicio de pelea, no una herramienta de movilidad.
```

El campo `rationale` es obligatorio y es **la mitad del mecanismo**: obliga a que cada respuesta
esperada tenga por escrito el hecho del kit que la sostiene. Una honeypot sin justificación
escribible no entra al catálogo.

**Quién y cuándo:** las redacta el alumno en la semana 5, junto con la implementación de este
módulo, y las revisa Marinozi antes del lanzamiento cerrado de la semana 7. La revisión no es
opinión sobre la respuesta: es verificar que cada `rationale` describa efectivamente lo que hace la
habilidad.

**Por parche:** `questions_identity` incluye `patch_id`, así que el catálogo se recarga en cada
parche. La mayoría de los pares sobrevive sin cambios —el kit de un campeón rara vez cambia— pero
un rework obliga a revisar los pares que lo incluyen.

### 3.4 Cómo sabemos que la respuesta es la correcta

Dos capas, una antes y una después.

**Antes — la justificación escrita.** El `rationale` tiene que describir un hecho del kit. "Yasuo
tiene un dash y Malphite no" es verificable por cualquiera que abra el juego. "Yasuo se siente más
móvil" no lo es, y esa honeypot no entra.

**Después — el monitoreo del *pass rate*.** Ningún criterio a priori es infalible, así que el
sistema vigila sus propias honeypots. `refresh_question_stats` calcula, para cada honeypot, la
proporción de respondedores que la contestan como se espera:

> Si el *pass rate* de una honeypot cae por debajo de **0.85**, la honeypot se retira
> automáticamente (`is_honeypot = false`) y **se recalcula el trust de todos los respondedores que
> la habían recibido**, como si nunca hubiera existido.

Porque cuando el 30 % de la gente falla una honeypot, la explicación abrumadoramente más probable no
es que el 30 % de la gente sea negligente: es que **la honeypot está mal**. Un parche cambió al
campeón, el par se volvió discutible, o el `rationale` era más débil de lo que parecía.

**El monitoreo sólo retira honeypots, nunca las crea.** Promover una pregunta a honeypot porque la
comunidad está de acuerdo sería circular: convertiría el consenso en verdad y penalizaría a quien
disiente, que es precisamente lo que §3.1 prohíbe. El catálogo se escribe a mano desde el kit; los
datos sólo pueden sacar cosas de él.

Como control cruzado, el Informe de Calidad de Datos reporta la correlación entre fallar honeypots y
las otras señales. Si quienes fallan una honeypot son consistentes en todo lo demás, la sospechosa
es la honeypot.

### 3.5 Cómo puntúa

| Respuesta | Efecto |
|---|---|
| Coincide con `expected_answer` | `honeypot_attempts += 1`, `honeypot_passed += 1` |
| No coincide | `honeypot_attempts += 1` |
| `unknown` | **Nada.** Ni intento ni fallo |

**`unknown` es neutro a propósito.** Penalizar "no estoy seguro" empuja a adivinar, y una adivinanza
entra al crudo como si fuera una opinión — ruido permanente en la tabla que no se puede corregir
después. Es preferible perder la oportunidad de medir a esa persona en esa pregunta que ganar una
respuesta inventada.

La comparación es una igualdad de `jsonb` contra `expected_answer`, que usa exactamente la misma
forma que `answer` (`11-modelo-de-datos.md` §5).

### 3.6 Cadencia

1 cada 10–15 preguntas, en posición aleatoria dentro de esa ventana (`20-tipos-de-pregunta.md` §7).
La posición se sortea al abrir cada ventana, no se fija: una honeypot que cayera siempre en la
posición 12 sería detectable por alguien que contara.

La cadencia se lleva **por respondedor**, contra `answers_count`, no por sesión. Quien responde 8 por
día durante una semana recibe honeypots con la misma frecuencia que quien responde 60 de un tirón.

---

## 4. Test-retest — RF-203

Cada ~30 preguntas se repite una que **ese mismo respondedor** ya contestó hace 15 o más preguntas.

- La distancia mínima de 15 evita que la reconozca por memoria inmediata; no la elimina, la debilita.
- La repetición se registra como una fila nueva con `is_retest_of` apuntando a la original. El índice
  único `responses_one_per_question` la deja pasar porque tiene `WHERE is_retest_of IS NULL`.
- Se elige entre las que contestó con una opción definida: repetir una que había contestado
  `unknown` no mide nada.

**Qué cuenta como consistente**, por tipo:

| Tipo | Consistente si… |
|---|---|
| 1 — pareada | La opción es idéntica. `unknown` en cualquiera de las dos: no cuenta el par |
| 3 — matchup | Los dos niveles caen del mismo lado o ambos en `even`; `a_strong` contra `a_slight` **cuenta como consistente** |
| 2 — pico | Los dos minutos difieren en 5 o menos |
| 4 — sinergia | La opción es idéntica |
| 5 — atributos | El índice de Jaccard entre los dos conjuntos es ≥ 0.60 |

La tolerancia del tipo 3 y del tipo 2 es deliberada: **se está midiendo consistencia, no memoria.**
Alguien que dice "gana Darius fuerte" y quince preguntas después "gana Darius apenas" no está
contestando al azar; alguien que dice "gana Darius fuerte" y después "gana Garen fuerte", sí.

Cada retest actualiza `retest_pairs` y, si corresponde, `retest_consistent`.

---

## 5. Patrones degenerados — RF-204

Los detecta el job diario `detect_degenerate_patterns`, que recorre las respuestas del día sobre el
índice `responses_by_respondent`.

### 5.1 Respuesta apurada

`response_time_ms < 800`. El umbral sale del piso de lectura: el enunciado más corto del sistema
—`"Who has more mobility?"` más dos nombres de campeón— no se lee y se decide en menos de 800 ms.

Cada respuesta por debajo incrementa `fast_answers`. **Una sola respuesta rápida no significa nada**
—alguien que ya sabía la respuesta al ver los retratos— y por eso la señal entra al trust como una
proporción sobre el volumen, no como un evento.

### 5.2 *Straightlining*

**Ocho respuestas consecutivas en la misma posición de opción**, sobre preguntas del mismo tipo.
Cada racha detectada incrementa `straightline_runs`.

Se cuenta por **posición en pantalla**, no por contenido: alguien que responde "izquierda,
izquierda, izquierda…" está tocando el mismo píxel, no eligiendo el mismo campeón. Como el sampler
no ordena las opciones de forma consistente, la probabilidad de que ocho respuestas seguidas caigan
del mismo lado por azar es 2 · (1/2)⁸ ≈ 0.8 %.

El umbral de 8 —y no 5— evita marcar a quien atraviesa una racha legítima: en `cc`, un tramo de
comparaciones donde el campeón A resulta ser siempre el de más control es perfectamente posible.

### 5.3 Qué NO se detecta

No se marca a quien responde mucho, ni a quien responde rápido pero consistente, ni a quien disiente
del consenso. **Disentir no es una señal de calidad mala.** Un respondedor que contesta distinto a
la mayoría pero es consistente consigo mismo y pasa los honeypots es exactamente el dato valioso que
el proyecto busca: alguien que sabe algo que la mayoría no.

---

## 6. Deduplicación por huella — RF-208

### 6.1 El ataque

RF-110 impide que un respondedor conteste dos veces la misma pregunta. Pero **borrar las cookies lo
evita**: como no hay login ([ADR-001](13-adr/ADR-001-sin-autenticacion.md)), una cookie nueva es una
identidad nueva. Alguien que quiera inflar el score de un campeón, o subir en la tabla de
posiciones, tiene que fabricar identidades.

Una **identidad** es una fila de `respondents`: una cookie, un `respondent_id`.

### 6.2 La detección

`fingerprint_hash` = SHA-256(user-agent + hash de IP + resolución de pantalla). Irreversible, y su
único uso es éste (RF-004).

El job diario `flag_duplicate_fingerprints` cuenta, para cada huella, cuántas identidades
**se crearon** en las últimas 24 horas:

```sql
UPDATE respondents SET is_flagged = true
WHERE fingerprint_hash IN (
    SELECT fingerprint_hash FROM respondents
    WHERE first_seen > now() - interval '24 hours'
    GROUP BY fingerprint_hash
    HAVING count(*) > 5
);
```

**Se cuenta por `first_seen`, no por `last_seen`.** La señal que interesa es la *creación* de
identidades, que es lo que produce el borrado de cookies. Contar por actividad marcaría una PC
compartida legítima —un cyber, un laboratorio— donde seis personas distintas responden el mismo día
desde identidades creadas hace semanas, que no es el comportamiento que se busca detectar.

Se marcan **todas** las identidades de esa huella, incluida la primera: no hay forma de saber cuál
era la "original", y suponerlo sería inventar información (CA-306).

Y como todo en este módulo, **ninguna respuesta se borra**. Las de un respondedor marcado quedan en
`responses` y sólo dejan de entrar a la agregación y a la tabla de posiciones.

### 6.3 Los falsos positivos se aceptan y se declaran

El umbral de 5 tiene un falso positivo conocido: **una red compartida con equipos clonados**. Una
sala de la UTN con la misma imagen de Windows, la misma resolución, el mismo Chrome y una salida NAT
única produce una huella idéntica para todas las máquinas. Si seis personas abren DraftSense en esa
sala el mismo día, las seis quedan marcadas.

Se decidió **dejar el umbral en 5 y convivir con eso**, en vez de subirlo o de agregar más
componentes a la huella:

- Subir el umbral debilita la detección justo donde importa, y con el volumen del piloto un solo
  respondedor determinado puede mover un score.
- Agregar componentes a la huella (zona horaria, idioma, `devicePixelRatio`) la acercaría a un
  identificador único de dispositivo, en tensión con RNF-05 y con lo que promete
  `33-privacidad-y-legal.md`. **Un mecanismo antifraude no puede costar el compromiso de privacidad
  del sistema.**

Lo que sí se hace con el costo aceptado:

1. **El umbral es un parámetro**, no una constante: `quality.fingerprint_max_identities` en
   `app_settings`. Si una jornada presencial va a producir un pico, se sube para esa ventana y se
   vuelve a bajar, y el cambio queda en `admin_audit`.
2. **Se reporta.** El Informe de Calidad de Datos incluye la cantidad de respondedores marcados por
   huella, cuántas respuestas quedaron fuera por esa causa y la advertencia explícita de que una
   parte puede ser una red compartida. Es un límite declarado del instrumento, no un detalle oculto.
3. **Se revisa el panel después del lanzamiento cerrado de la semana 7**, que es la actividad más
   expuesta al falso positivo por ser presencial y en ámbito académico.

---

## 7. El trust score — RF-205, RF-206, RF-207

### 7.1 La fórmula

```
h     = (honeypot_passed   + 2 · 0.5) / (honeypot_attempts + 2)      # honeypots, suavizado
r     = (retest_consistent + 2 · 0.5) / (retest_pairs      + 2)      # consistencia, suavizado
d     = min(1, (fast_answers + 2 · straightline_runs) / max(20, 0.15 · answers_count))

trust = clamp(0, 1, (0.60 · h + 0.40 · r) · (1 - 0.50 · d))
```

Tres decisiones adentro de esa fórmula:

**El suavizado bayesiano (`+2 · 0.5`) evita el juicio con un solo dato.** Sin él, fallar el primer
honeypot daría `h = 0` y un trust de 0.20, que es una condena a partir de una observación. Con él,
un respondedor nuevo —sin honeypots ni retests— da exactamente `h = r = 0.5` y `trust = 0.500`, que
es el `DEFAULT` de la columna. **La fórmula y el default coinciden por construcción**, no por
casualidad: no hay un estado inicial artificial que después la fórmula contradiga.

**Los patrones degenerados multiplican en vez de sumar.** Son un descuento sobre lo que las otras dos
señales dicen, no una tercera opinión. Alguien que pasa todos los honeypots y es consistente pero va
demasiado rápido conserva la mayor parte de su trust; alguien que además falla honeypots se hunde
por los dos lados.

**El denominador de `d` tiene un piso de 20.** Sin él, tres respuestas rápidas sobre las primeras
cinco respuestas darían `d = 1` y castigarían a alguien que apenas empezó.

Valores de referencia, útiles para el test de CA-302:

| Situación | `trust` |
|---|---|
| Respondedor nuevo, sin datos | **0.500** |
| Falla su primer honeypot | **0.400** |
| Pasa su primer honeypot | **0.600** |
| 5 de 5 honeypots fallados | **0.286** — cae bajo el umbral del export |
| 10/10 honeypots, 8/10 retests, sin patrones | **0.850** |

### 7.2 Cuándo se recalcula

- **Sincrónico**, en la misma transacción del `INSERT`, cuando la pregunta era honeypot o retest.
  Es una operación aritmética sobre columnas de la propia fila del respondedor: no toca `responses`
  y no compromete el presupuesto de 150 ms de `POST /responses`.
- **Diferido**, en el job `detect_degenerate_patterns`, cuando cambian `fast_answers` o
  `straightline_runs`.
- **Masivo**, cuando se retira una honeypot (§3.4): se recalcula el de todos los respondedores que
  la habían recibido.

`trust_score` es una **caché**: se puede reconstruir entero desde `responses` más los catálogos de
honeypots y los retests. Un job de verificación lo recalcula desde cero y compara, para detectar
divergencias por un error de contador.

### 7.3 Uso dual

| Uso | Dónde | Cómo |
|---|---|---|
| **Peso** | Agregación | `peso(r) = trust_score · 0.5^(dias/vida_media)` ([ADR-004](13-adr/ADR-004-ventana-de-parches-con-decaimiento.md)) |
| **Filtro** | Exportación | Las respuestas con `trust_score < min_trust` no entran. `min_trust` es parámetro de la corrida y queda en `exports.min_trust_applied` |
| **Filtro** | Tabla de posiciones | Ver [`23-gamificacion.md`](23-gamificacion.md) §5 |

El umbral inicial es **0.30**. Es la primera estimación y se calibra con los datos reales del piloto
antes de la entrega final; el valor de cada corrida queda registrado, así que el laboratorio puede
pedir un reanálisis con otro. Con la fórmula de §7.1, cruzar 0.30 hacia abajo requiere fallar unas
cinco honeypots: no es un accidente.

### 7.4 Nunca se expone — RF-207

No aparece en `GET /me`, ni en `GET /leaderboard`, ni en el feedback post-respuesta, ni en ninguna
métrica derivada de la que se pueda despejar.

Exponerlo convertiría la calidad en un juego a optimizar en vez de una consecuencia de responder
honestamente — y alguien que ve su trust bajar aprende a evitar la detección, no a responder mejor.
El único lugar donde vive es el panel de administración, detrás de `X-Admin-Key`, y ahí como
distribución agregada.

---

## 8. Parámetros

Todos en `app_settings` (RF-606):

| Clave | Valor inicial | Qué controla |
|---|---|---|
| `quality.honeypot_every` | `[10, 15]` | Ventana de cadencia de honeypots |
| `quality.honeypot_min_pass_rate` | `0.85` | Bajo este valor la honeypot se retira sola |
| `quality.retest_every` | `30` | Cadencia de retests |
| `quality.retest_min_distance` | `15` | Distancia mínima a la respuesta original |
| `quality.fast_answer_ms` | `800` | Umbral de respuesta apurada |
| `quality.straightline_run` | `8` | Respuestas seguidas en la misma posición |
| `quality.fingerprint_max_identities` | `5` | Identidades por huella en 24 h antes de marcar |
| `quality.trust_weights` | `{"honeypot":0.60,"retest":0.40,"degenerate":0.50}` | Pesos de la fórmula |
| `quality.trust_smoothing` | `2` | Fuerza del suavizado bayesiano |
| `export.min_trust` | `0.30` | Umbral por defecto del filtro de exportación |

---

## 9. Verificación

| Qué se prueba | Cómo | CA |
|---|---|---|
| La honeypot es indistinguible | El JSON de `GET /questions/next` no contiene `is_honeypot` ni `expected_answer` en ninguna forma | CA-103 |
| Cadencia | 60 preguntas seguidas producen entre 4 y 6 honeypots, y ninguna ventana de 15 queda vacía | CA-301 |
| La fórmula | Un respondedor en 0.500 que falla su primer honeypot queda en **0.400** | CA-302 |
| `unknown` es neutro | Responder `unknown` a una honeypot deja `honeypot_attempts` sin cambios | CA-308 |
| Retiro automático | Una honeypot que baja de 0.85 de pass rate queda con `is_honeypot = false` y los trust afectados se recalculan | CA-309 |
| El trust no se filtra | El valor no aparece en `/me` ni en `/leaderboard`, ni se puede despejar de ninguna métrica publicada | CA-303 |
| Apuradas | Una respuesta de menos de 800 ms incrementa el contador y recalcula el trust | CA-304 |
| Straightlining | Ocho respuestas consecutivas en la misma posición marcan la racha | CA-305 |
| Huella duplicada | Seis identidades de una huella en 24 h quedan las seis marcadas, sin borrar ninguna respuesta | CA-306 |
| Marcado excluye | Las respuestas de un marcado no entran a la agregación pero siguen en `responses` | CA-307 |

---

Ver el índice en [`README.md`](README.md) y las decisiones cerradas en [`13-adr/`](13-adr/).
