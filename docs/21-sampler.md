# 21 — Sampling adaptativo

> Estado: **v1** · Última revisión: 01/09/2026 · Ola 3 · Desbloquea la semana 5 del cronograma

Cómo el sistema decide **qué pregunta mostrar a continuación**. Es el componente que convierte un
presupuesto chico de respuestas —1 000 comprometidas, unos miles como meta de trabajo— en un
conjunto de datos con intervalos de confianza utilizables en vez de uno ralo y disperso.

Requerimientos que implementa: RF-101, RF-110, RF-111, RF-201, RF-203, RF-604.

---

## 1. El problema

El sampler tiene un presupuesto fijo y tres presiones que tiran en direcciones distintas:

1. **Cobertura.** Cada campeón necesita comparaciones suficientes en cada dimensión para que su
   intervalo sea angosto.
2. **Información.** Una pregunta cuya respuesta ya es unánime no aporta casi nada; una disputada
   aporta mucho.
3. **Conectividad.** Bradley-Terry necesita que el grafo de comparaciones esté conectado, y nada en
   las dos presiones anteriores lo garantiza ([ADR-008](13-adr/ADR-008-conectividad-por-componentes.md)).

Elegir al azar cubre parejo pero desperdicia muestra en preguntas ya resueltas. Elegir sólo por
información se encierra en un subconjunto de campeones parecidos y parte el grafo. El sampler
combina las tres presiones en una función de prioridad, con una válvula de exploración que impide
que la explotación lo encierre.

---

## 2. Generación perezosa — RF-111

### 2.1 Qué prohíbe el requerimiento

`questions` tiene una fila **por pregunta concreta**: un par específico, con su dimensión, su rol o
su contexto de dupla, y su parche. Precomputar todas las combinaciones posibles del pool sería lo
natural y es exactamente lo que RF-111 prohíbe.

Cuántas filas serían, **por parche**:

| Tipo | Tier 1 (40) | Tier 1+2 (80) | Catálogo (170) |
|---|---|---|---|
| 1 — pareada × 8 dimensiones | 6 240 | 25 280 | 114 920 |
| 3 — 1v1 por rol | ~200 | ~800 | ~3 700 |
| 2 y 5 — una por campeón | 80 | 160 | 340 |
| 3-2v2 y 4 — pares de duplas | ~10 000 | ~110 000 | **~10⁶** |
| **Total** | **~17 000** | **~136 000** | **> 1 000 000** |

Y eso se multiplica por parche, porque `questions_identity` incluye `patch_id`. Con cinco o seis
parches en la práctica, el catálogo completo precomputado son varios millones de filas, de las
cuales se van a responder entre 10 000 y 15 000 (`11-modelo-de-datos.md` §8). El 99 % quedaría con
`exposure_count = 0` para siempre, ensuciando el índice `questions_sampler` y obligando a
`refresh_question_stats` a recorrer basura cada 15 minutos, en contra de RNF-01.

El término dominante son las duplas: el espacio de pares de duplas es el cuadrado del espacio de
duplas, que a su vez es cuadrático en el catálogo. Ahí precomputar no es caro, es inviable.

### 2.2 Cómo se genera

El sampler trabaja sobre **combinaciones**, no sobre filas. Una combinación es una tupla
`(type, champion_a..d, dimension_id, role, duo_ctx, patch_id)` que existe conceptualmente aunque no
esté en la base. Sólo se materializa la fila cuando la pregunta efectivamente se va a mostrar:

```sql
INSERT INTO questions (type, patch_id, champion_a, champion_b, dimension_id, role, duo_ctx)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT ON CONSTRAINT questions_identity DO UPDATE
    SET exposure_count = questions.exposure_count      -- no-op: fuerza el RETURNING
RETURNING question_id, exposure_count, entropy;
```

El `DO UPDATE` con una asignación que no cambia nada es intencional: `ON CONFLICT DO NOTHING` no
devuelve fila cuando hay conflicto, y acá se necesita el `question_id` tanto si la pregunta es nueva
como si ya existía. Es la forma estándar de un *upsert con RETURNING* en Postgres.

Consecuencias:

- La tabla crece con el **uso real**, no con la combinatoria.
- **Habilitar el tier 2 no genera nada.** Sólo amplía el espacio del que el sampler muestrea. Es lo
  que hace verdadera la promesa de [ADR-006](13-adr/ADR-006-pool-escalonado-por-pick-rate.md): promover
  un campeón es un `UPDATE`, no un despliegue.
- Toda combinación tiene su forma canónica antes del `INSERT` (`champion_a < champion_b`, y en las
  variantes de dupla también `champion_c < champion_d` y `champion_a < champion_c`), así que
  `(A,B)` y `(B,A)` colisionan en el mismo `question_id` en vez de duplicarse.

### 2.3 El espacio de combinaciones habilitado

```
campeones habilitados = champions WHERE is_active AND pool_tier <= app_settings['sampler.enabled_pool_tiers']
```

`enabled_pool_tiers` vive en `app_settings` (`11-modelo-de-datos.md` §3.12), no en el código ni en
una variable de entorno: se cambia desde el panel de administración y toma efecto en la próxima
pregunta, sin desplegar (RF-604, RF-606).

Restricciones adicionales por tipo, que recortan el espacio antes de muestrear:

| Tipo | Restricción |
|---|---|
| 1 — pareada | Cualquier par de campeones habilitados; toda dimensión activa |
| 2 — pico | Cualquier campeón habilitado |
| 3 — 1v1 | Ambos campeones deben tener el rol en `champions.roles`, y el rol debe ser `top`, `mid` o `adc` |
| 3 — 2v2 | Las cuatro entidades forman dos duplas válidas de `bot`: un `adc` y un `support` cada una |
| 4 — sinergia | Las dos duplas comparten el mismo `duo_ctx` y sus campeones tienen los roles que ese contexto exige |
| 5 — atributos | Cualquier campeón habilitado |

---

## 3. La función de prioridad

Sobre las preguntas **ya materializadas** con soporte suficiente para tener estadísticas, la
prioridad es una suma ponderada de cuatro términos, todos normalizados a `[0,1]`:

```
prioridad(q) = 0.35 · escasez(q)
             + 0.25 · informacion(q)
             + 0.20 · deficit_cobertura(q)
             + 1.00 · puente(q)
```

### 3.1 Los cuatro términos

| Término | Fórmula | Qué empuja |
|---|---|---|
| `escasez(q)` | `1 / (1 + exposure_count)` | Preguntar lo que menos se preguntó |
| `informacion(q)` | `entropy` normalizada, ver §3.2 | Insistir donde la comunidad está dividida |
| `deficit_cobertura(q)` | `coverage_deficit`, ver §3.3 | Atender al campeón peor cubierto del par |
| `puente(q)` | `1` si `bridge_priority`, si no `0` | Conectar componentes separadas del grafo |

**El peso del puente es 1.00 y no 0.30 a propósito.** Los otros tres suman como máximo 0.80, así que
cualquier pregunta puente supera a cualquier pregunta no-puente sin importar el resto. Es la forma de
expresar "prioridad máxima por encima de escasez y entropía" —lo que pide
[ADR-008](13-adr/ADR-008-conectividad-por-componentes.md)— dentro de una sola fórmula, sin un caso
especial en el código ni un `ORDER BY` de dos niveles.

Los cuatro pesos viven en `app_settings` bajo `sampler.weights`.

### 3.2 `informacion(q)` — la entropía, por tipo

`questions.entropy` es `numeric(5,4)` con `CHECK (entropy BETWEEN 0 AND 1)`, así que cada tipo
define su propia normalización a ese rango. La calcula `refresh_question_stats` desde
`answer_counts`:

| Tipo | Entropía |
|---|---|
| 1 — pareada | Entropía binaria sobre `{a, b}`, **ignorando `unknown`**: `H(p) = -p·log₂p - (1-p)·log₂(1-p)` con `p = a/(a+b)` |
| 3 — 1v1 y 2v2 | Los 5 niveles se colapsan a `{gana A, parejo, gana B}` y se toma la entropía de Shannon dividida por `log₂ 3` |
| 4 — sinergia | Entropía de Shannon sobre `{pair_1, similar, pair_2}` dividida por `log₂ 3` |
| 2 — pico | `min(1, IQR / 12)` sobre los minutos declarados: la dispersión hace de entropía |
| 5 — atributos | Promedio de las entropías binarias de los 7 atributos |

**`unknown` se excluye del cálculo, no se cuenta como una tercera opción.** Una pregunta con 40 %
de `unknown` y el resto repartido 50-50 está tan disputada como una sin ningún `unknown`: la
incertidumbre sobre *qué campeón* es la misma. Meter `unknown` adentro de la entropía haría que
"esta dimensión no aplica" se confunda con "esta comparación está reñida", que son dos cosas
distintas y se miden por separado — la primera es `D_unknown_rate` en el export.

### 3.3 `deficit_cobertura(q)` — sin agregar en vivo

El déficit de una pregunta es el del campeón peor cubierto que la integra:

```
n_max        = mediana de n sobre todos los (campeón, dimensión) del parche vigente
deficit(c,d) = max(0, (n_max - n(c,d)) / n_max)
coverage_deficit(q) = max sobre los campeones de q de deficit(c, dimension(q))
```

**No se calcula en el camino crítico.** `GET /questions/next` tiene un presupuesto de 100 ms p95 y
no puede hacer un `GROUP BY` sobre `responses`. El valor se guarda denormalizado en
`questions.coverage_deficit` y lo mantiene `refresh_question_stats` cada 15 minutos, igual que
`exposure_count`, `answer_counts` y `entropy`. El sampler sólo lee columnas indexadas.

Que el valor esté hasta 15 minutos desactualizado es irrelevante: es una prioridad relativa, no una
decisión que se pueda equivocar.

---

## 4. Los dos regímenes y la exploración

### 4.1 Por qué hacen falta

Dos de los tres términos informativos **necesitan datos que al arrancar no existen**: la entropía de
una pregunta sin respuestas no está definida, y el déficit de cobertura se calcula contra una mediana
global que con cero respuestas es cero. Sin una regla explícita, el sampler arranca operando sobre
ruido ([ADR-012](13-adr/ADR-012-sampler-uniforme-en-arranque-en-frio.md)).

Hay además un problema estructural: si el sampler sólo ordena **filas existentes**, nunca genera
combinaciones nuevas y se queda encerrado en las primeras que materializó. Las combinaciones que
todavía no existen no tienen estadísticas y por lo tanto no pueden competir en la función de
prioridad.

### 4.2 La solución: un solo mecanismo

Las candidatas se parten en dos estratos por `exposure_count`:

| Estrato | Condición | Cómo se elige adentro |
|---|---|---|
| **Frío** | `exposure_count < 5`, **incluidas las combinaciones que todavía no existen** | Muestreo uniforme |
| **Caliente** | `exposure_count >= 5` | Función de prioridad §3 |

Y una única probabilidad `ε` decide a cuál ir:

```
si existe alguna pregunta con bridge_priority no respondida por este respondedor:
    devolverla                                        # el puente gana siempre
si random() < ε:
    muestrear UNIFORMEMENTE una combinación del espacio habilitado    # exploración
    materializarla con el upsert de §2.2
si no:
    devolver la de mayor prioridad del estrato caliente               # explotación
```

**Lo elegante es que la rama de exploración no distingue entre "pregunta fría existente" y
"combinación nueva".** Muestrea uniformemente sobre el espacio de combinaciones y el `ON CONFLICT`
resuelve el resto: al principio casi todos los sorteos caen en combinaciones inexistentes y se
materializan; a medida que la tabla se llena, cada vez más sorteos caen en filas ya creadas y el
`upsert` devuelve la existente. La transición del arranque en frío al régimen normal es continua y
automática, sin un interruptor que alguien tenga que accionar.

El umbral de 5 y el muestreo uniforme adentro del estrato frío son exactamente lo que fija ADR-012.

### 4.3 El valor de ε

`ε` es un parámetro de `app_settings` (`sampler.epsilon`), no una constante. Cronograma previsto:

| Momento | `ε` | Por qué |
|---|---|---|
| Lanzamiento cerrado, semana 7 | `1.00` | No hay nada que explotar: todo es exploración, que es literalmente lo que dice ADR-012 |
| Lanzamiento público, semana 8 | `0.30` | Ya hay señal, pero el pool de tier 1 todavía no está sembrado parejo |
| Régimen normal, semana 9 en adelante | `0.20` | Una de cada cinco preguntas sigue explorando, para no encerrarse |

**El valor es un juicio, no un hecho.** Se calibra observando dos indicadores en el panel: la
fracción de preguntas del estrato caliente y el ancho medio de los intervalos por dimensión. Si el
ancho baja pero la cobertura se estanca, `ε` está bajo; si la cobertura avanza pero los intervalos no
se angostan, está alto.

### 4.4 Muestreo uniforme sin enumerar

La rama de exploración necesita sortear una combinación **sin materializar el espacio**, que es
justamente lo que RF-111 prohíbe. Se hace sorteando componente por componente:

```python
def combinacion_al_azar(tipo, pool, dimensiones_activas, rng):
    if tipo == "pairwise_dimension":
        a, b = rng.sample(pool, 2)
        return canonica(a, b), rng.choice(dimensiones_activas)
    if tipo == "lane_matchup_1v1":
        rol = rng.choice(["top", "mid", "adc"])
        candidatos = [c for c in pool if rol in c.roles]
        a, b = rng.sample(candidatos, 2)
        return canonica(a, b), rol
    ...
```

Es uniforme sobre el espacio de combinaciones válidas de ese tipo y cuesta O(1) más el filtro por
rol, que se resuelve con el índice GIN `champions_roles_gin` o directamente en memoria: el catálogo
son 170 filas y se cachea al arrancar el proceso.

---

## 5. Exclusión de lo ya respondido — RF-110

Un respondedor no puede recibir dos veces la misma pregunta, salvo que sea un retest deliberado.

- **Rama de explotación:** se piden las **50 mejores** por prioridad y se descartan en memoria las
  que el respondedor ya contestó. 50 alcanza de sobra: un respondedor con 1 500 respuestas —el tope
  diario— sigue teniendo disponible la enorme mayoría del estrato caliente.
- **Rama de exploración:** rechazo con reintento. Se sortea, se verifica, y si ya la contestó se
  vuelve a sortear, hasta 10 veces. Con un espacio de decenas de miles de combinaciones, la
  probabilidad de 10 colisiones seguidas es despreciable.
- **Fallback:** si las 10 fallan, se cae a la rama de explotación. Si esa también se queda sin
  candidatas, ver §8.

El conjunto de preguntas ya respondidas por el respondedor se carga **una vez por lote**, no una vez
por pregunta: `GET /questions/next?count=5` hace una sola consulta sobre `responses_by_respondent`.

---

## 6. Composición de la sesión

La mezcla de tipos y las reglas de `20-tipos-de-pregunta.md` §7 se aplican **antes** de elegir cuál
pregunta dentro del tipo. El sampler primero decide *qué tipo* toca en la posición `k` de la sesión,
después usa §3 y §4 para elegir la pregunta concreta.

| Regla | Detalle | Prioridad |
|---|---|---|
| Arranque | Las primeras 3 preguntas de un respondedor nuevo son siempre de tipo 1 | 1ª |
| Honeypot | 1 cada 10–15, en posición aleatoria dentro de la ventana | 2ª |
| Retest | 1 cada 30, repitiendo una que contestó hace 15 o más preguntas | 3ª |
| Variedad | No más de 3 seguidas del mismo tipo | 4ª |
| Mezcla | 50 / 20 / 15 / 5 / 5 / 5 entre los tipos | 5ª |

El orden importa: cuando dos reglas chocan, gana la de arriba. Una honeypot que caiga en la posición
2 desplaza la tercera pregunta de tipo 1, no al revés — porque medir calidad temprano vale más que
la comodidad del arranque.

La cadencia de honeypot y retest se lleva **por respondedor**, contra `answers_count`, no por
sesión: alguien que responde 8 preguntas por día durante una semana tiene que recibir honeypots con
la misma frecuencia que quien responde 60 de un tirón.

Detalle de las honeypots en [`22-calidad-de-datos.md`](22-calidad-de-datos.md); las honeypots y los
retests **no pasan por la función de prioridad**: se eligen de su propio catálogo.

---

## 7. Promoción de tier

Era una decisión abierta de este documento. Dos mecanismos distintos, que no hay que confundir:

### 7.1 Promover un campeón — `champions.pool_tier`

Al cargar el snapshot de pick rate de un parche nuevo, un campeón de tier 2 pasa a tier 1 si entra
en el **top 12 de su rol por `rank_in_role`** en la tabla `pick_rate_entries` de ese snapshot; y uno
de tier 1 baja a tier 2 si cae fuera del top 20. La histéresis entre 12 y 20 evita que un campeón
oscile entre tiers en parches consecutivos, que rompería su continuidad de soporte muestral.

Es un `UPDATE` derivado de un dato versionado en el repositorio, no un juicio del administrador
([ADR-006](13-adr/ADR-006-pool-escalonado-por-pick-rate.md)).

### 7.2 Habilitar el tier siguiente — `app_settings['sampler.enabled_pool_tiers']`

Ampliar el pool **diluye** la muestra: los mismos respondedores repartidos sobre el doble de
campeones. Sólo se justifica cuando el pool actual ya produce datos utilizables. Criterio numérico:

> Se habilita el tier 2 cuando, sobre los campeones de tier 1 y las 8 dimensiones, la **mediana de
> `D_n` alcanza 25** —el umbral de `solid` de `26-esquema-de-salida.md` §2.4— **y** el grafo de
> comparaciones está conectado en al menos **6 de las 8 dimensiones**.

Las dos condiciones juntas, no una. La mediana sola podría alcanzarse con un grafo partido en dos
mitades densas, que es el peor escenario posible: mucha muestra y ningún orden global.

El panel muestra ambos indicadores, así que la decisión se toma mirando un número, no una intuición.
Con el volumen esperado del piloto es **improbable que la condición se cumpla**, y eso está bien: el
plan por defecto es cerrar la práctica con datos densos sobre 40 campeones.

---

## 8. Casos borde

| Situación | Comportamiento |
|---|---|
| El pool habilitado tiene menos de 2 campeones con un rol | Ese rol no genera preguntas de tipo 3. No es un error: se registra en el log y el tipo se saltea en la mezcla |
| Una dimensión se desactiva (`is_active = false`) | Deja de generar preguntas nuevas al instante. Las respuestas ya dadas **no se tocan** y siguen entrando a la agregación |
| El respondedor agotó todo lo disponible | Se le sirven retests. Es prácticamente imposible con el tope de 1 500/día contra un espacio de decenas de miles, pero el camino existe y está probado |
| `refresh_question_stats` lleva horas detenido | El sampler sigue operando con valores viejos: pierde precisión progresivamente y **no falla**. La rama de exploración es inmune, porque no usa estadísticas |
| Hay más de 50 preguntas puente | Se ordenan entre sí por la función de prioridad completa y se sirve la mejor |
| Dos peticiones concurrentes materializan la misma combinación | El índice único `questions_identity` la deduplica; el `upsert` devuelve el mismo `question_id` a ambas |

---

## 9. Parámetros

Todos en `app_settings`, ninguno en el código (RF-606):

| Clave | Valor inicial | Qué controla |
|---|---|---|
| `sampler.enabled_pool_tiers` | `1` | Hasta qué tier genera preguntas |
| `sampler.epsilon` | `1.00` → `0.20` | Probabilidad de explorar (§4.3) |
| `sampler.weights` | `{"escasez":0.35,"informacion":0.25,"cobertura":0.20,"puente":1.00}` | Pesos de la prioridad |
| `sampler.cold_threshold` | `5` | Respuestas para pasar al estrato caliente (ADR-012) |
| `sampler.consensus_threshold` | `20` | Respuestas para mostrar el feedback de consenso (ADR-012, RF-114) |
| `sampler.candidate_limit` | `50` | Cuántas candidatas trae la rama de explotación |
| `sampler.max_rejection_retries` | `10` | Reintentos de la rama de exploración |

### Frecuencia de los jobs

Era la otra decisión abierta. Valores de arranque, a validar contra el costo observado en el plan
gratuito:

| Job | Frecuencia | Se revisa si… |
|---|---|---|
| `refresh_question_stats` | 15 min | El plan gratuito limita las ejecuciones, o el job tarda más de 2 min |
| `check_graph_connectivity` | 1 h | Aparecen componentes partidas y se necesita reaccionar más rápido |
| `detect_degenerate_patterns` | diaria | — |
| `flag_duplicate_fingerprints` | diaria | — |

Con el volumen del piloto —miles de respuestas, no millones— los cuatro jobs corren en segundos. La
frecuencia está limitada por lo que permite el plan gratuito, no por el costo de cómputo.

---

## 10. Pseudocódigo completo

```python
def siguiente_pregunta(respondent, posicion, ya_respondidas, cfg):
    tipo = tipo_para_posicion(respondent, posicion, cfg)      # §6

    if toca_honeypot(respondent, cfg):
        return honeypot_no_vista(respondent)                  # 22-calidad-de-datos §3
    if toca_retest(respondent, cfg):
        return retest_de(respondent, cfg)                     # 22-calidad-de-datos §4

    puente = mejor_puente(tipo, ya_respondidas)               # ADR-008
    if puente:
        return puente

    if random() < cfg["sampler.epsilon"]:                     # exploración
        for _ in range(cfg["sampler.max_rejection_retries"]):
            comb = combinacion_al_azar(tipo, pool_habilitado(cfg), dimensiones_activas())
            q = upsert_question(comb)                         # §2.2
            if q.question_id not in ya_respondidas:
                return q

    candidatas = top_por_prioridad(                           # explotación, §3
        tipo, limite=cfg["sampler.candidate_limit"])
    for q in candidatas:
        if q.question_id not in ya_respondidas:
            return q

    return retest_de(respondent, cfg)                         # §8, último recurso
```

---

## 11. Verificación

| Qué se prueba | Cómo |
|---|---|
| No se precomputa | Tras 100 peticiones sobre un pool de 40 campeones, `count(*)` de `questions` es del orden de las preguntas servidas, no de 6 240 |
| La generación es idempotente | Materializar la misma combinación dos veces devuelve el mismo `question_id` y no crea una fila nueva |
| La forma canónica funciona | Sortear `(B,A)` y `(A,B)` produce una sola fila |
| El puente domina | Una pregunta con `bridge_priority` y `exposure_count` alto le gana a una sin puente y `exposure_count = 0` |
| El régimen frío es uniforme | Con `ε = 1` y 10 000 sorteos, la distribución de campeones es uniforme dentro del error de muestreo |
| Nadie repite pregunta | Un respondedor que pide 200 preguntas no recibe dos veces el mismo `question_id`, salvo retests |
| La mezcla se respeta | Sobre 100 preguntas, las proporciones por tipo están dentro de ±5 puntos de 50/20/15/5/5/5 |

Los criterios formales están en [`03-criterios-aceptacion.md`](03-criterios-aceptacion.md) §2.

---

Ver el índice en [`README.md`](README.md) y las decisiones cerradas en [`13-adr/`](13-adr/).
