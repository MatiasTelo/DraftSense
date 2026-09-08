# 25 — Pipeline de agregación: del respondedor al CSV

> Estado: **v1** · Última revisión: 03/09/2026 · Ola 4 · Desbloquea la semana 9 del cronograma

Qué hace exactamente el sistema con cada dato que produce una persona —los tres que declara al
entrar y cada respuesta que da después— desde que la fila entra a `responses` hasta que sale como
una celda de un CSV.

Es el complemento de [`26-esquema-de-salida.md`](26-esquema-de-salida.md): aquél define **qué**
contiene cada columna, éste define **cómo se calcula**. Ninguna magnitud del contrato de entrega
queda sin fórmula acá.

Requerimientos que implementa: RF-005, RF-206, RF-501 a RF-510, RF-512.

---

## 0. El recorrido de un dato

```
   respondents                      responses                    questions
   ───────────                      ─────────                    ─────────
   declared_rank        ─┐          answer (jsonb)               type, dimension,
   declared_main_role    ├─ ✗ ─►    response_time_ms             role, duo_ctx,
   declared_hours_bucket─┘          created_at, patch_id         champion_a..d
          │                              │                            │
          │ segmentación                 │                            │
          │ (nunca peso)                 │                            │
          ▼                              ▼                            ▼
   Informe de Calidad     ┌──────────────────────────────────────────────┐
   de Datos               │ 1 · filtro de la corrida            (§1)     │
   (§3.4 a §3.8)          │ 2 · peso = trust · decaimiento      (§2)     │
                          │ 3 · estimador según el tipo         (§5)     │
   trust_score ──────────►│ 4 · bootstrap → intervalo           (§4.2)   │
   (22-calidad-de-datos)  │ 5 · centrado, _n, _support, formato (§4)     │
                          └──────────────────────────────────────────────┘
                                             │
                     ┌───────────────────────┼───────────────────────┐
                     ▼                       ▼                       ▼
            champion_features.csv    matchup_matrix.csv      duo_features.csv
                 126 columnas            12 columnas            18 columnas
```

La flecha tachada es el punto que más se malinterpreta y por eso está en el mapa: **lo que el
respondedor declara sobre sí mismo no toca ninguna estimación**. Lo que sí la toca es su
`trust_score`, que el sistema deriva de cómo responde, no de lo que dice ser (§3.3).

---

## 1. Qué entra a una corrida

### 1.1 La consulta base

```sql
WITH ventana AS (
    SELECT patch_id
    FROM patches
    WHERE released_at BETWEEN (SELECT released_at FROM patches WHERE version = :desde)
                          AND (SELECT released_at FROM patches WHERE version = :hasta)
)
SELECT r.response_id, r.respondent_id, r.question_id, r.type,
       r.answer, r.created_at, r.patch_id,
       q.champion_a, q.champion_b, q.champion_c, q.champion_d,
       q.dimension_id, q.role, q.duo_ctx,
       p.trust_score
FROM responses  r
JOIN questions  q USING (question_id)
JOIN respondents p ON p.respondent_id = r.respondent_id
WHERE r.patch_id       IN (SELECT patch_id FROM ventana)
  AND r.is_retest_of   IS NULL          -- §1.3
  AND NOT q.is_honeypot                 -- §1.3
  AND NOT p.is_flagged                  -- 22 §6
  AND p.trust_score    >= :min_trust    -- 26 §2.6
ORDER BY r.response_id;
```

**La ventana se resuelve por `released_at`, no comparando `patches.version` como texto.** Las
versiones son cadenas con el formato `\d+\.\d+`, y como texto `'16.9'` es mayor que `'16.20'`: un
`BETWEEN` sobre la versión daría una ventana silenciosamente equivocada en cuanto un parche pase de
`.9` a `.10`.

El `ORDER BY response_id` no es decorativo: el bootstrap se alimenta de esta lista y CA-408 exige
que dos corridas con los mismos parámetros produzcan archivos idénticos bit a bit (§8.3).

### 1.2 Los cinco filtros

| Filtro | Qué deja afuera | Por qué |
|---|---|---|
| Ventana de parches | Respuestas de parches fuera de la ventana | Un campeón cambia entre parches; la ventana es el compromiso entre pureza y volumen ([ADR-004](13-adr/ADR-004-ventana-de-parches-con-decaimiento.md)) |
| `is_retest_of IS NULL` | La segunda respuesta de un retest | §1.3 |
| `NOT is_honeypot` | Las respuestas a preguntas trampa | §1.3 |
| `NOT is_flagged` | Todo el historial de un respondedor marcado | Huella duplicada: no hay forma de saber cuál identidad era la original (22 §6.2) |
| `trust_score >= min_trust` | Todo el historial de quien queda bajo el umbral | El umbral es parámetro de la corrida y queda en `exports.min_trust_applied` |

**Nada se borra.** Los cinco filtros son cláusulas de un `SELECT` sobre una tabla append-only
([ADR-002](13-adr/ADR-002-responses-append-only.md)): correr de nuevo con `min_trust = 0.10`
devuelve un conjunto distinto sin haber tocado un solo byte del crudo.

### 1.3 Por qué los honeypots y los retests no entran

Son las dos exclusiones que no vienen de un documento previo y se deciden acá.

**Los honeypots quedan afuera por circularidad.** Una respuesta a un honeypot es un insumo del
`trust_score` del respondedor, y el `trust_score` es el peso de toda respuesta suya. Si esa misma
fila fuera además un dato del campeón, el dato estaría ponderándose a sí mismo. A eso se suma que
el catálogo de honeypots se elige por un criterio deliberadamente no aleatorio —pares cuya
respuesta es obvia desde el kit (22 §3.1)— así que unos 40 pares por parche recibirían una fracción
enorme de las respuestas del tipo 1 sólo por diseño del instrumento de calidad, no por decisión del
sampler.

**Los retests quedan afuera para no contar dos veces a la misma persona.** El índice
`responses_one_per_question` garantiza una respuesta por (respondedor, pregunta) precisamente
porque una opinión repetida no es evidencia nueva; el retest es la excepción deliberada a ese
índice y existe para medir consistencia, no para aportar peso. La respuesta original sí entra, con
todo su peso.

### 1.4 Qué se hace con "no sé", "even", "similar" y la lista vacía

Los cinco tipos tienen una opción que no elige un ganador. **Ninguna es un dato faltante, y ninguna
se trata igual:**

| Tipo | Opción | Qué se hace con ella |
|---|---|---|
| 1 — pareada | `choice: "unknown"` | Fuera del ajuste de Bradley-Terry; **entra a `D_unknown_rate`** (§5.1) |
| 2 — pico | *(no existe)* | Un slider no tiene "no sé": si no lo movió, lo delata `response_time_ms` |
| 3 — matchup | `choice: "even"` | **Es un dato.** Lo consume el umbral `τ₁` del modelo ordinal (§5.3) |
| 4 — sinergia | `choice: "similar"` | **Es un dato.** Lo consume el umbral `τ` (§5.5) |
| 5 — atributos | `traits: []` | **Es un dato.** Suma al denominador de los 7 atributos y al numerador de ninguno (§5.6) |

La única que sale del ajuste es `unknown` del tipo 1, y no se pierde: se publica como tasa porque
dice algo del par —que la dimensión probablemente no aplica— que el score no puede decir.

---

## 2. El peso de una respuesta

### 2.1 La fórmula

```
peso(r) = trust_score(respondedor(r)) · 0.5 ^ ( dias(r) / H )

dias(r) = exported_at − date(r.created_at)          en días enteros
H       = aggregation.decay_halflife_days           inicial 21
```

Es la única ponderación del pipeline. Los dos factores están decididos en documentos previos —el
trust en [`22-calidad-de-datos.md`](22-calidad-de-datos.md) §7.3, el decaimiento en
[ADR-004](13-adr/ADR-004-ventana-de-parches-con-decaimiento.md)— y acá sólo se combinan.

### 2.2 Qué significan esos números

| Antigüedad | Factor de recencia | Respondedor nuevo (trust 0.500) | Respondedor probado (trust 0.850) |
|---|---|---|---|
| Mismo día | 1.000 | 0.500 | 0.850 |
| 14 días (un parche) | 0.631 | 0.316 | 0.536 |
| 21 días | 0.500 | 0.250 | 0.425 |
| 42 días (tres parches) | 0.250 | 0.125 | 0.213 |
| 42 días, trust 0.30 (mínimo) | 0.250 | 0.075 | — |

La relación entre el máximo y el mínimo peso admisible es de **1 a 13**: una respuesta reciente de
alguien con trust 0.95 pesa trece veces lo que una de hace seis semanas de alguien apenas por
encima del umbral. Es mucho, y es intencional; lo que importa es que **ninguna respuesta admitida
pesa cero** —eso sería excluirla en silencio, que es lo que [ADR-011](13-adr/ADR-011-support-level-en-vez-de-excluir.md)
prohíbe— y que la escala de pesos no depende de quién dice ser nadie.

**Por qué 21 días como valor inicial de `H`:** los parches salen cada dos semanas y la ventana
típica de una corrida son tres parches (unos 42 días). Con `H = 21` la respuesta más vieja de la
ventana conserva un cuarto de su peso: sigue aportando a la conectividad del grafo y al soporte
muestral, pero no compite con la evidencia del parche vigente. Un `H` mucho más corto desperdicia
muestra —el cuello de botella del piloto—; uno mucho más largo mezcla campeones que ya cambiaron.
Se recalibra con los datos del piloto y el valor de cada corrida queda registrado.

### 2.3 El peso no es una opinión sobre la persona

Conviene decirlo explícitamente porque de acá sale toda la §3: el peso de una respuesta se compone
de **cómo respondió** (honeypots, consistencia consigo mismo, patrones degenerados) y de **cuándo
respondió**. No entra qué rango dice tener, ni cuántas horas dice jugar, ni qué rol dice ser el
suyo.

---

## 3. Los tres datos declarados: rol, tiempo de juego y rango

### 3.1 Qué son exactamente

Se piden una sola vez, en `/start`, en una pantalla con `Skip` siempre visible
([`30-ux-flujos.md`](30-ux-flujos.md) §4), y se guardan en tres columnas de `respondents`
(RF-005, [`11-modelo-de-datos.md`](11-modelo-de-datos.md) §3.7):

| Columna | Tipo | Valores admitidos | Qué pregunta la pantalla |
|---|---|---|---|
| `declared_rank` | text | `iron` `bronze` `silver` `gold` `platinum` `emerald` `diamond` `master` `grandmaster` `challenger` `unranked` | *Your rank* |
| `declared_main_role` | `lane_role` | `top` `jungle` `mid` `adc` `support` | *Main role* |
| `declared_hours_bucket` | text | `<5` `5-15` `15-30` `30+` | *Hours per week* |

Los tres admiten `NULL`, y `NULL` significa **"omitió o prefirió no decir"**, que es distinto de
`unranked` (juega, pero no clasificatoria) y distinto de cualquier bucket de horas.

Son **categorías gruesas a propósito**. Se pregunta el tier del rango, no la división exacta; un
rango de horas, no un número. Tres variables categóricas anchas no identifican a nadie, que es lo
que permite pedirlas sin login y sin consentimiento de datos personales
(RNF-05, [ADR-001](13-adr/ADR-001-sin-autenticacion.md)).

### 3.2 Lo que no hacen — las cuatro puertas cerradas

| No hacen | Detalle |
|---|---|
| **No ponderan** | No aparecen en `peso(r)` (§2.1). Una respuesta de un *challenger* declarado y una de un *iron* declarado pesan exactamente lo mismo si tienen el mismo trust y la misma antigüedad |
| **No filtran** | Ningún valor —ni `NULL`— excluye a nadie de una corrida. Los filtros son los cinco de §1.2 y ninguno los menciona |
| **No dirigen el sampler** | A nadie se le muestran preguntas distintas por lo que declaró. El sampler decide por escasez, entropía, déficit de cobertura y puente ([`21-sampler.md`](21-sampler.md) §3), sobre variables de la pregunta, no del respondedor |
| **No salen en ningún CSV** | Las tres salidas son a nivel campeón o par de campeones. Ninguna de las 126 + 12 + 18 columnas contiene un atributo de una persona, ni siquiera agregado |

### 3.3 Por qué no ponderan

Es la decisión importante de esta sección, y tiene tres razones que se sostienen solas.

**No son verificables.** No hay login, no hay cuenta de Riot vinculada, no hay forma de contrastar
lo declarado ([ADR-001](13-adr/ADR-001-sin-autenticacion.md)). Un peso construido sobre un campo de
autorreporte es un peso que se puede elegir: bastaría marcar *Challenger* para valer más. Todo el
módulo de calidad está construido sobre señales que el respondedor **no controla desde el
formulario** —si pasa honeypots, si es consistente consigo mismo, a qué velocidad responde—
precisamente para que la calidad sea una consecuencia de responder bien y no un campo a completar
(22 §7.4).

**Ponderar por rango asume lo que el proyecto quiere medir.** Dar más peso a los rangos altos
equivale a afirmar que su opinión sobre *cuánto engage tiene Alistar* es más correcta. Puede que lo
sea; puede que no lo sea parejo en todas las dimensiones. Es una hipótesis contrastable, y §3.5 la
contrasta. Meterla como peso la volvería incontrastable: el resultado la confirmaría por
construcción.

**Sesga hacia el consenso de un subgrupo.** El instrumento existe para medir lo que la comunidad
sabe, con su dispersión. Un esquema de pesos por rango declarado empuja el resultado hacia el
consenso del segmento privilegiado y angosta artificialmente los intervalos, que son justamente el
producto que el laboratorio recibe.

Lo que sí se hace con las tres variables son los cinco usos que siguen.

### 3.4 Uso 1 — Describir la muestra

El Informe de Calidad de Datos abre con quién produjo los datos. Para cada una de las tres
variables se publica una tabla con **dos columnas de conteo**:

| Bucket | Respondedores | % resp. | Respuestas | % de las respuestas |
|---|---|---|---|---|
| `platinum` | 34 | 22 % | 1 208 | 31 % |
| … | … | … | … | … |
| *(no dijo)* | 71 | 46 % | 902 | 23 % |

**Las dos columnas de conteo no son redundantes y ésa es la razón de la tabla.** Un puñado de
personas muy activas puede aportar la mitad de las respuestas: la distribución por respondedor dice
quiénes participaron, la distribución por respuestas dice quiénes efectivamente movieron los
números. Cuando difieren mucho, es un límite del instrumento que hay que declarar.

Se reporta además el **índice de concentración**: qué fracción de las respuestas aporta el decil más
activo de respondedores. Es el número que decide si el bootstrap actual es defendible (§4.7).

### 3.5 Uso 2 — Estabilidad por segmento de rango (RF-511)

El análisis que justifica la decisión de §3.3. El procedimiento es el mismo pipeline, corrido varias
veces sobre subconjuntos:

1. Se agrupan los once valores de `declared_rank` en cinco segmentos —tres de rango, más `unranked`,
   más quienes no declararon— para que cada uno tenga muestra utilizable:

   | Segmento | `declared_rank` |
   |---|---|
   | `low` | `iron` `bronze` `silver` |
   | `mid` | `gold` `platinum` `emerald` |
   | `high` | `diamond` `master` `grandmaster` `challenger` |
   | `unranked` | `unranked` |
   | `undeclared` | `NULL` |

2. Para cada segmento se vuelve a ajustar el modelo de las **8 dimensiones del tipo 1**, usando sólo
   las respuestas de los respondedores de ese segmento y exactamente los mismos parámetros de la
   corrida principal.

3. Se comparan los ajustes entre sí, no contra el ajuste global (comparar contra el global sería
   comparar cada segmento contra un promedio que lo contiene):

   | Métrica | Qué responde |
   |---|---|
   | ρ de Spearman entre los órdenes de dos segmentos, por dimensión | ¿ordenan igual a los campeones? |
   | Diferencia absoluta media de los scores centrados | ¿cuánto se separan en magnitud? |
   | Campeones que cambian de `support_level` | ¿el desacuerdo se concentra donde hay poca muestra? |

4. **Umbral mínimo para reportar un segmento:** 15 respondedores y 300 comparaciones utilizables en
   esa dimensión. Por debajo, el segmento se reporta como *no calculable* con su `n`, nunca con un
   número frágil. Con el volumen del piloto es un desenlace probable y hay que poder decirlo.

**Cómo se lee el resultado.** Un ρ alto entre `low` y `high` es el mejor argumento que el proyecto
puede dar: significa que la medición no depende de a quién se le preguntó, y por lo tanto que una
muestra abierta y anónima es un instrumento válido. Un ρ bajo **no invalida el CSV**: lo convierte
en un límite declarado, y en el insumo de la decisión de §3.10.

El mismo análisis se corre con `declared_hours_bucket`, que es la otra variable ordenada.

### 3.6 Uso 3 — Cobertura por rol de las magnitudes que dependen del rol

`declared_main_role` no está ordenado, así que la comparación de §3.5 no aplica igual. Lo que sí
aporta es una advertencia de validez sobre tres columnas concretas.

`lane_strength_top`, `lane_strength_mid` y `lane_strength_adc` salen de preguntas sobre un carril
específico. El Informe de Calidad de Datos publica, por cada rol, **qué fracción de las respuestas
de tipo 3 sobre ese rol vino de gente que declaró jugarlo como principal**:

```
lane_strength_adc :  1 402 respuestas ·  9 % de mains de adc ·  38 % sin rol declarado
```

Un 9 % no invalida la columna —la pregunta es sobre campeones, no sobre la experiencia propia— pero
es información que el laboratorio merece tener antes de construir un modelo sobre esa columna. Y es
la métrica que justificaría, si quedara muy baja, pedir difusión dirigida en el plan piloto en vez
de tocar el estimador.

Se reporta la misma fracción para `duo_features.lane_strength`, que depende de opiniones sobre el
carril inferior.

### 3.7 Uso 4 — Validar el trust score desde afuera

`declared_hours_bucket` es lo más parecido a una medida de exposición al juego que el sistema tiene,
y sirve para una comprobación que ninguna señal interna puede hacer: **¿el trust score mide algo
real, o sólo mide atención?**

Se reporta la distribución de `trust_score` por bucket de horas. Si el trust fuera ruido, no habría
relación. Una relación positiva y suave —quien juega más pasa más honeypots— es evidencia de que las
honeypots capturan conocimiento del juego, que es lo que dicen medir (22 §3.1).

Es un control, no un objetivo. Si la relación fuera fuertísima, la sospecha sería la contraria: que
los honeypots están midiendo horas de juego en vez de atención, y el catálogo necesita revisión.

### 3.8 Uso 5 — Auditar el catálogo de honeypots

22 §3.4 exige vigilar el *pass rate* de cada honeypot y retirarla automáticamente por debajo de
0.85. El rango declarado agrega un control cruzado que el pass rate global no da: **el pass rate por
segmento**.

Una honeypot buena se falla parejo poco en todos los segmentos. Una que los segmentos altos fallan
tanto como los bajos es sospechosa de estar mal redactada, no de estar detectando negligencia.
Es exactamente la lectura que 22 §3.4 pide ("si quienes fallan una honeypot son consistentes en
todo lo demás, la sospechosa es la honeypot"), con una variable más para sostenerla.

Este uso **no retira honeypots por sí solo**: el retiro automático sigue siendo el del pass rate
global. Alimenta la revisión manual del catálogo.

### 3.9 Qué se hace con los `NULL`

| Regla | Detalle |
|---|---|
| Nunca se imputan | No se rellena con la moda ni con nada. `NULL` es un valor, no un hueco |
| Nunca se descartan | Un respondedor que omitió el onboarding aporta igual que cualquier otro |
| Son su propio segmento | `undeclared` aparece en toda tabla de §3.4 a §3.8, con su `n` |
| Se reporta su tamaño primero | Si el 60 % omite, todo análisis por segmento cubre una minoría, y eso se dice antes de mostrar el análisis |

Omitir el onboarding es una respuesta explícita del producto —`Skip` llama al endpoint con los tres
campos en `null` (CA-005)— y el análisis la trata como tal.

### 3.10 Qué haría falta para cambiar de opinión

Si el análisis de §3.5 mostrara que los segmentos ordenan distinto de forma consistente, la
respuesta correcta **no** sería ponderar por rango declarado —seguiría sin ser verificable— sino
**post-estratificar**: reponderar los segmentos para que su participación en la muestra coincida con
una distribución objetivo (por ejemplo la distribución pública de rangos del juego).

Tres cosas hay que decir sobre eso, y las tres son límites de esta práctica:

1. **Está fuera de alcance.** Requiere una distribución objetivo defendible y un tratamiento del
   segmento `undeclared`, que no tiene lugar en ninguna distribución objetivo. Sería un ADR nuevo.
2. **El laboratorio no puede hacerlo por su cuenta con lo que se entrega**, porque los CSV son a
   nivel campeón: el segmento de quien respondió ya está integrado fuera. Hacerlo requeriría una
   salida adicional por segmento.
3. **El disparador está definido:** si en §3.5 el ρ de Spearman entre `low` y `high` cae por debajo
   de 0.70 en tres o más dimensiones con muestra suficiente, se registra como hallazgo en el Informe
   de Calidad de Datos y se propone la salida por segmento como trabajo futuro.

Dejarlo escrito con su disparador es lo que separa un límite conocido de un descuido.

---

## 4. El bloque común a toda magnitud

Las 20 magnitudes de `champion_features` y las 3 de las otras dos salidas comparten el mismo
esqueleto. Se define una vez acá y §5 sólo especifica el estimador.

### 4.1 El valor

Cada estimador de §5 produce un número por entidad (campeón, par o dupla). Los que salen de un
modelo de Bradley-Terry están identificados **salvo una constante aditiva**: sumar 3 a todos los
scores describe exactamente los mismos datos. Se fija esa constante centrando:

```
θ_i ← θ_i − media( θ_j : j en el pool exportado con estimación en esa corrida )
```

La media es sin ponderar por soporte: es un cambio de origen, no una estimación. El alcance del
centrado cambia según la magnitud, y está en la tabla de §6.

### 4.2 El intervalo de confianza

Bootstrap no paramétrico sobre las comparaciones, `B = 2 000` remuestreos
([`26-esquema-de-salida.md`](26-esquema-de-salida.md) §3.2):

```
para b en 1..B:
    muestra_b ← remuestreo con reemplazo de las comparaciones filtradas (§1.1), mismo tamaño
    θ_b       ← ajustar el estimador sobre muestra_b, con los mismos pesos
    θ_b       ← centrar θ_b        ← imprescindible, ver abajo
IC_95(i) = percentiles 2.5 y 97.5 de { θ_b(i) : b = 1..B }
```

**Re-centrar dentro de cada iteración no es un detalle.** Sin ese paso, la indeterminación aditiva
del modelo se cuela en la distribución bootstrap y todos los intervalos salen inflados por una
varianza que no existe en el dato. Es el error clásico al bootstrapear Bradley-Terry.

Tres reglas más:

- **La semilla se deriva de los parámetros de la corrida**, no del reloj (CA-408):
  `seed = int(sha256(f"{patch_window}|{min_trust}|{H}|{sigma}|{B}|{aggregation_version}").hexdigest()[:16], 16)`.
- Si un remuestreo deja **el grafo desconectado** en esa dimensión, se descarta y se sortea otro,
  hasta 3·B intentos. Si se descarta más del 5 % de los remuestreos, la dimensión entera se marca
  `insufficient` y el hecho va al Informe de Calidad de Datos: un intervalo calculado sobre
  remuestreos seleccionados no es un intervalo del 95 %.
- Los remuestreos de las 8 dimensiones son **independientes entre sí**. No se busca un intervalo
  conjunto: cada columna se lee sola.

### 4.3 `_n`

Siempre un **conteo crudo de respuestas, sin ponderar**. Lo dice el nombre —soporte muestral— y lo
exige la comparabilidad: un `_n` ponderado sería un número que se mueve al cambiar `min_trust` o la
vida media, y dejaría de significar "cuánta gente contestó esto".

Qué cuenta exactamente cambia por magnitud y está en §6. Las respuestas `unknown` del tipo 1 nunca
cuentan en `_n`, porque no entraron al ajuste.

### 4.4 `_support`

Función de `_n` y del **ancho del intervalo** (`_ci_high − _ci_low`), con los umbrales de
[`26-esquema-de-salida.md`](26-esquema-de-salida.md) §2.4. Dos precisiones que ese documento deja
abiertas y se cierran acá:

| Magnitud | Juego de umbrales que se aplica |
|---|---|
| `matchup_matrix.support` | El de **Fuerza de línea** (`n ≥ 20` y ancho `≤ 0.60`), sobre `n_responses` y el ancho de `advantage_ci` |
| `duo_features.lane_strength_support` | El de **Sinergia** (`n ≥ 15` y ancho `≤ 0.80`), no el de Fuerza de línea |

La segunda merece explicación: la unidad muestral de `duo_features` es la dupla, y el espacio de
duplas es de otro orden de magnitud que el de campeones. Exigirle a una dupla los 20 casos que se le
exigen a un campeón marcaría el archivo entero como `insufficient` y volvería inútil la columna.
Es el mismo criterio que ya aplica el fixture de [`examples/`](examples/).

La primera es una deuda declarada: `advantage` vive en `−1…+1` y `lane_strength` en log-odds, así
que el mismo número de ancho no significa lo mismo en las dos escalas. Es uno de los umbrales a
recalibrar con los datos del piloto, y el valor efectivamente usado queda registrado en `exports`.

### 4.5 Vacío no es cero

Se aplica la regla de 26 §2.3 sin excepciones: sin datos ⇒ celda **vacía**, `_n = 0`,
`_support = insufficient`, y `_ci_low` / `_ci_high` también vacíos.

La única situación donde una celda tiene valor con `_n = 0` es una **predicción del modelo**, y
entonces la fila lo declara en su columna `is_observed` (§5.4, §5.5). Fuera de las dos salidas
pareadas, que tienen esa columna, `_n = 0` implica celda vacía.

### 4.6 Formato numérico

Fijo, porque de él depende que el SHA-256 sea reproducible (CA-408).

| Qué | Formato | Ejemplo |
|---|---|---|
| Scores en log-odds y sus IC | `%.3f` | `-0.180` |
| Proporciones (`trait_*`, `_norm`) y sus IC | `%.3f` | `0.040` |
| `*_unknown_rate` | `%.2f` | `0.34` |
| `power_at_*` | `%.2f` | `0.65` |
| `peak_minute` y su IC | entero | `22` |
| `_n` | entero | `148` |
| Booleanos | `true` / `false` en minúscula | `false` |
| Vacío | cadena vacía | `,,` |

Codificación UTF-8 sin BOM, fin de línea `\n`, separador `,`, sin comillas salvo que el valor las
necesite. Orden de filas: `champion_features` por `champion_id`; `matchup_matrix` por
`(role, champion_a_id, champion_b_id)`; `duo_features` por
`(duo_context, champion_a_id, champion_b_id)`.

### 4.7 Límite conocido: el bootstrap no agrupa por respondedor

26 §3.2 fija el bootstrap **sobre las comparaciones**, y así está especificado arriba. Vale decir
qué supone eso: que dos comparaciones son observaciones independientes. No lo son del todo —una
misma persona aporta decenas, y sus sesgos viajan con todas—, así que **los intervalos publicados
son, en alguna medida, más angostos que los honestos**.

La alternativa es un bootstrap **por respondedor**: remuestrear personas con reemplazo y tomar todas
sus respuestas. Es la unidad de independencia correcta, pero con pocos respondedores ensancha mucho
los intervalos y rompe la conectividad del grafo en una fracción alta de los remuestreos.

Cómo se resuelve, sin cambiar el contrato por cuenta propia:

1. La corrida calcula **las dos versiones** del intervalo y publica la de 26; el Informe de Calidad
   de Datos reporta el ancho medio de ambas, por dimensión.
2. El criterio de decisión es el índice de concentración de §3.4: si el decil más activo de
   respondedores aporta **más del 40 %** de las comparaciones, la diferencia entre ambos bootstraps
   deja de ser académica y corresponde un ADR que reemplace lo fijado en 26 §3.2.
3. Se decide en la semana 10, con los datos del piloto sobre la mesa, no antes.

---

## 5. Los estimadores, uno por tipo de pregunta

### 5.1 Tipo 1 → las 8 dimensiones

**Entra:** respuestas `pairwise_dimension` con `choice ∈ {a, b}`, agrupadas por `dimension_id`.
**Sale:** 56 columnas de `champion_features` (7 por dimensión).
**Corridas:** una **independiente por dimensión**. Nada se comparte entre dimensiones.

#### El modelo

Bradley-Terry: la probabilidad de que la comunidad elija a `i` sobre `j` es

```
P(i ≻ j) = exp(θᵢ) / ( exp(θᵢ) + exp(θⱼ) )
```

La verosimilitud sólo depende de los **conteos ponderados de victorias**, así que las respuestas se
colapsan primero en una matriz:

```
W[i][j] = Σ peso(r)   sobre las respuestas donde se eligió a i frente a j
N[i][j] = W[i][j] + W[j][i]
Wᵢ      = Σⱼ W[i][j]
```

y se ajusta con la iteración MM de Hunter (2004), que admite conteos fraccionarios de forma nativa
—que es exactamente lo que son los pesos de §2:

```
repetir hasta |Δ log π| < 1e-9 (máx. 500 iteraciones):
    para cada i:
        πᵢ ← ( Wᵢ + ε ) / ( Σⱼ≠ᵢ N[i][j] / (πᵢ + πⱼ)  +  2ε / (πᵢ + 1) )
    normalizar π a media geométrica 1
θᵢ = log πᵢ
```

La implementación usa `choix` sobre la misma matriz densa de comparaciones ponderadas (ILSR, que es
un acelerador de esta misma iteración, [ADR-003](13-adr/ADR-003-bradley-terry.md)); el pseudocódigo
de arriba es la **definición** del estimador y el test lo compara contra el resultado de la
biblioteca.

**Qué es `ε`.** Un regularizador de valor inicial 0.5, equivalente a media victoria y media derrota
contra un oponente promedio. Existe por una razón numérica y sólo por ésa: un campeón que ganó todas
sus comparaciones tiene `θ = +∞` sin él. Encoge hacia 0 a quien tiene poquísimos datos, que es el
comportamiento deseable.

> `ε` **no** es la regularización bayesiana que [ADR-008](13-adr/ADR-008-conectividad-por-componentes.md)
> descarta. Aquella se usaría para inventar un orden entre componentes desconectadas; ésta sólo
> mantiene finito el ajuste **dentro** de una componente. La conectividad se sigue detectando y
> reportando como manda el ADR (§7).

#### Las siete columnas

| Columna | Cómo se calcula |
|---|---|
| `D` | `θᵢ` centrado sobre los campeones del export con estimación en esa dimensión (§4.1) |
| `D_ci_low`, `D_ci_high` | Bootstrap de §4.2 sobre las comparaciones de esa dimensión |
| `D_n` | Conteo crudo de respuestas con `choice ∈ {a,b}` en las que participa el campeón, en esa dimensión |
| `D_support` | Umbrales de Dimensiones: `n ≥ 25` y ancho `≤ 0.60` → `solid` |
| `D_unknown_rate` | `Σ peso(unknown) / Σ peso(todas, incluidas unknown)` sobre las preguntas de esa dimensión que involucran al campeón |
| `D_norm` | `(D − mín) / (máx − mín)` sobre el export. Vacía si menos de 2 campeones tienen valor |

`D_unknown_rate` se pondera y `D_n` no, y la diferencia es deliberada: `_n` responde "cuánta gente
contestó" y tiene que ser un conteo; la tasa de `unknown` es una proporción como cualquier otra del
export y se pondera igual que todas.

### 5.2 Tipo 2 → pico de poder y curva

**Entra:** respuestas `peak_timing` del campeón. **Sale:** 10 columnas.

```
peak_minute = redondeo( mediana_ponderada( minutos, pesos ) )
```

Mediana ponderada: se ordenan los minutos de menor a mayor, se acumulan los pesos y se toma el valor
donde el acumulado alcanza la mitad del peso total; si cae exactamente en el borde entre dos
valores, se promedian los dos. El resultado se redondea al entero más cercano porque el instrumento
es un slider de enteros y publicar `21.7` sugeriría una precisión que la pregunta no tiene.

**Mediana y no media**, por [`20-tipos-de-pregunta.md`](20-tipos-de-pregunta.md) §3: un puñado de
sliders arrastrados a 0 o a 40 desplaza una media y casi no mueve una mediana.

```
power_at(t) = exp( −(t − peak_minute)² / (2 · σ²) )      para t ∈ {5, 10, 15, 20, 25}
```

con `σ = aggregation.power_sigma`, inicial 7.5 ([ADR-009](13-adr/ADR-009-curva-de-poder-gaussiana.md)).
Se evalúa sobre el **`peak_minute` entero ya exportado**, no sobre la mediana sin redondear, para que
quien lea el CSV pueda recalcular las cinco columnas y obtener exactamente los mismos números.

| Columna | Cómo se calcula |
|---|---|
| `peak_minute` | Mediana ponderada redondeada |
| `peak_minute_ci_*` | Bootstrap sobre las respuestas del campeón, mediana ponderada en cada remuestreo, percentiles redondeados |
| `peak_minute_n` | Conteo crudo de respuestas de tipo 2 sobre el campeón |
| `peak_minute_support` | Umbrales de Pico: `n ≥ 20` y ancho `≤ 4 min` → `solid` |
| `power_at_5` … `power_at_25` | Fórmula de arriba. **Vacías si `peak_minute` está vacío** |

### 5.3 Tipo 3, variante 1v1 → fuerza de línea y matriz de matchups

**Entra:** respuestas `lane_matchup` con `role ∈ {top, mid, adc}`.
**Sale:** 15 columnas de `champion_features` y las filas de `matchup_matrix`.
**Corridas:** una **independiente por rol**.

#### El modelo ordinal

Cinco niveles ordenados exigen más que un Bradley-Terry con empates. Se usa la extensión natural de
Rao-Kupper a **dos umbrales**, con la restricción de simetría que hace que el modelo no dependa de
cuál campeón quedó como `a` en el orden canónico. Con `δ = θₐ − θ_b` y `σ(x) = 1/(1+e⁻ˣ)`:

```
P(a_strong) = σ(δ − τ₂)
P(a_slight) = σ(δ − τ₁) − σ(δ − τ₂)
P(even)     = σ(δ + τ₁) − σ(δ − τ₁)
P(b_slight) = σ(δ + τ₂) − σ(δ + τ₁)
P(b_strong) = 1 − σ(δ + τ₂)

con 0 < τ₁ < τ₂, compartidos por todos los pares del rol
```

Las cinco suman 1 por construcción, y `δ = 0` da una distribución simétrica centrada en `even`, que
es lo que debe pasar entre dos campeones equivalentes. Rao-Kupper clásico es el caso de un solo
umbral, es decir `τ₂ → ∞`: tres resultados en vez de cinco.

Se estima maximizando la verosimilitud ponderada `Σ peso(r) · log P(yᵣ | δ)` sobre `θ` y
`(τ₁, τ₂)` a la vez, con el mismo regularizador `ε` de §5.1 sobre `θ`. Optimizador: L-BFGS sobre
`(θ, log τ₁, log(τ₂ − τ₁))`, que impone `0 < τ₁ < τ₂` sin restricciones explícitas.

#### `advantage`: del modelo a la escala −1…+1

`26` §4 mapea los cinco niveles a `{a_strong: +1, a_slight: +0.5, even: 0, b_slight: −0.5,
b_strong: −1}`. Ese mapeo es lo que convierte el ajuste en la columna:

```
advantage(A, B, R) = Σₖ vₖ · P(Y = k | δ_AB)        v = (+1, +0.5, 0, −0.5, −1)
```

Es el **margen esperado** bajo el modelo ajustado. Cae en `(−1, +1)`, vale exactamente 0 cuando
`δ = 0`, y es antisimétrico —`advantage(B,A) = −advantage(A,B)`— porque las probabilidades lo son.
Por eso el archivo guarda una sola dirección.

Para un par observado, el valor es el promedio de sus respuestas *encogido hacia lo que el resto de
la red dice de esos dos campeones*, que es toda la ventaja de ajustar un modelo en vez de promediar.
Para un par nunca preguntado, es pura predicción del modelo.

| Columna | Cómo se calcula |
|---|---|
| `lane_strength_R` | `θᵢ` centrado **dentro del rol R**. Vacía si el campeón no juega ese rol |
| `lane_strength_R_ci_*` | Bootstrap sobre las comparaciones de ese rol |
| `lane_strength_R_n` | Conteo crudo de respuestas del campeón en ese rol |
| `matchup_matrix.advantage` | Fórmula de arriba |
| `matchup_matrix.advantage_ci_*` | `advantage` recalculado en cada remuestreo, percentiles 2.5 / 97.5 |
| `matchup_matrix.n_responses` | Conteo crudo de respuestas **a ese par concreto en ese rol** |
| `matchup_matrix.is_observed` | `n_responses > 0` |

**Qué pares tienen fila:** todos los `(a, b, R)` con `a_id < b_id` en los que ambos campeones están
en el export, ambos declaran el rol `R` en `champions.roles` y ambos tienen `lane_strength_R`
estimada. Un par sin respuestas entra igual, con `is_observed = false`, `n_responses = 0` y el
intervalo que le salga —notoriamente más ancho, porque depende de dos parámetros estimados y de
ningún dato propio (CA-406).

### 5.4 Tipo 3, variante 2v2 → `duo_features.lane_strength`

Mismo modelo ordinal de §5.3, con **la dupla como competidor** y una sola corrida, sobre
`duo_ctx = 'bot'`. La diferencia está en cómo se parametriza la fuerza de una dupla, que es lo que
permite que el archivo tenga filas predichas.

#### La fuerza de una dupla

```
θ_dupla(A,B) = a_A + a_B + i_AB

a_·   efecto de acompañante del campeón: cuánto aporta a cualquier dupla
i_AB  interacción propia de esa dupla: lo que tiene de específico
```

con penalización L2 sobre ambos términos, más fuerte sobre las interacciones
(`λ_i` ≫ `λ_a`, valores en §9). Consecuencias, que son exactamente el comportamiento que
[`26-esquema-de-salida.md`](26-esquema-de-salida.md) §5 y
[`20-tipos-de-pregunta.md`](20-tipos-de-pregunta.md) §5 ya describen:

- Una dupla **observada** tiene `i_AB` identificada por sus comparaciones: su valor es evidencia.
  `is_observed = true`.
- Una dupla **nunca preguntada** tiene `i_AB = 0` por construcción, y su valor es `a_A + a_B`: una
  predicción honesta a partir de lo que se sabe de cada integrante por separado.
  `is_observed = false`, `_n = 0`.
- Con el volumen del piloto, casi todas las `i_AB` quedan cerca de 0 y la mayoría de las filas del
  archivo son esencialmente aditivas. **Ésa es la razón de fondo por la que `duo_features` es la
  salida de soporte más flojo de las tres**, y por la que `is_observed` es la columna que hay que
  mirar primero.

**Qué duplas tienen fila:** las que participaron en al menos una comparación (de sinergia o de
carril), más las combinaciones válidas para el contexto en las que **ambos** integrantes tienen `a_·`
estimada. Sin ese segundo criterio el archivo sería el cuadrado del pool; con él, queda acotado a lo
que el modelo puede sostener.

`lane_strength` sólo se calcula para `duo_ctx = 'bot'`: es el único carril donde dos campeones
comparten oponentes durante la fase de líneas. En `top_jungle` y `mid_jungle` la columna queda
vacía, con `_n = 0` y `is_observed = false`.

### 5.5 Tipo 4 → `synergy` y `synergy_mean`

**Entra:** respuestas `duo_synergy`. **Corridas:** una **independiente por `duo_context`**.

Tres resultados (`pair_1`, `similar`, `pair_2`), así que el modelo es Rao-Kupper con **un solo
umbral** — el caso `τ₂ → ∞` de §5.3:

```
P(pair_1)  = σ(δ − τ)
P(similar) = σ(δ + τ) − σ(δ − τ)
P(pair_2)  = 1 − σ(δ + τ)
```

sobre la misma parametrización de dupla de §5.4 (`a_· + i_··`), ajustada por separado: son dos
magnitudes distintas y no comparten parámetros.

**Descartar los `similar` no es una opción.** En una comparación de baja señal es la respuesta más
frecuente, y tirarla dejaría el ajuste sobre el subconjunto de comparaciones decididas, que son las
menos representativas de lo que se está midiendo.

Cada corrida se centra en 0 **dentro de su contexto**: la sinergia de un dúo de bot y la de uno
mid-jungla no son comparables entre sí y no se las hace parecer comparables.

#### `synergy_mean`

```
synergy_mean(c)   = media( synergy(d) : d contiene a c, d con synergy_is_observed = true )
synergy_mean_n    = cantidad de esas duplas
```

Media **sin ponderar por soporte**: ponderar por `_n` premiaría a las duplas que el sampler eligió
más, que es una decisión de muestreo, no una señal de importancia. Cada `synergy(d)` ya lleva
adentro toda la evidencia ponderada de esa dupla.

Se promedia sobre los tres contextos juntos, y se puede porque cada uno está centrado en 0 dentro
del suyo.

`synergy_mean_support` necesita un ancho y la columna no publica intervalo (26 §3.5 explica por
qué): se usa **el ancho medio de los `synergy_ci` de las duplas promediadas**. Dice cuán precisas
son las estimaciones que entraron al promedio, sin afirmar un intervalo para el promedio mismo.

### 5.6 Tipo 5 → los 7 atributos

**Entra:** respuestas `trait_multiselect` del campeón. **Sale:** 35 columnas.

```
p̂(c, T) = Σ peso(r) · 1[ T ∈ r.traits ]  /  Σ peso(r)
```

sobre las respuestas de tipo 5 al campeón `c` **en las que el atributo `T` estaba activo**.
`{"traits": []}` suma al denominador y no al numerador: es "ninguno de estos", que es un dato
(CA-207).

El intervalo es de **Wilson al 95 %**, y el tamaño que entra en la fórmula no es `n` sino el
**tamaño muestral efectivo de Kish**, porque la proporción está ponderada:

```
n_eff = ( Σ peso )² / Σ peso²
```

`n_eff ≤ n` siempre, con igualdad sólo si todos los pesos son iguales. Usar `n` daría un intervalo
más angosto de lo que la muestra ponderada sostiene.

| Columna | Cómo se calcula |
|---|---|
| `trait_T` | `p̂` |
| `trait_T_ci_*` | Wilson 95 % con `p̂` y `n_eff` |
| `trait_T_n` | Conteo crudo de respuestas de tipo 5 sobre el campeón donde `T` estaba activo |
| `trait_T_support` | Umbrales de Atributos: `n ≥ 20` y ancho `≤ 0.25` → `solid`, sobre `_n` crudo |

**Los siete `trait_T_n` de una fila son idénticos salvo que un atributo se haya activado o
desactivado a mitad de la ventana.** Una respuesta marca los siete de una vez, así que el soporte es
por campeón; si difieren, o hubo un cambio de catálogo en la ventana —y el Informe de Calidad de
Datos lo dice— o hay un error en la agregación.

---

## 6. Trazabilidad columna por columna

### 6.1 `champion_features_v<patch>.csv` — 126 columnas

| Columnas | Bloque | Origen | Estimador | Centrado | `_n` cuenta |
|---|---|---|---|---|---|
| 1–7 | Identificación | `champions`, parámetros de la corrida | — | — | — |
| 8–63 | 8 dimensiones × 7 | Tipo 1 | §5.1 | Pool del export, por dimensión | Comparaciones del campeón en esa dimensión, sin `unknown` |
| 64–68 | `peak_minute` + IC + soporte | Tipo 2 | §5.2 | — | Respuestas de tipo 2 al campeón |
| 69–73 | `power_at_*` | Derivado de la col. 64 | §5.2 | — | *(sin `_n` propio)* |
| 74–88 | 3 roles × 5 | Tipo 3 · 1v1 | §5.3 | Dentro del rol | Respuestas del campeón en ese rol |
| 89–91 | `synergy_mean` | Tipo 4, vía `duo_features` | §5.5 | *(hereda el de cada dupla)* | Duplas observadas que lo incluyen |
| 92–126 | 7 atributos × 5 | Tipo 5 | §5.6 | — | Respuestas de tipo 5 al campeón |

### 6.2 `matchup_matrix_v<patch>.csv` — 12 columnas

| Columnas | Contenido | Cómo se calcula |
|---|---|---|
| 1–5 | Identificación del par y rol | Orden canónico `a_id < b_id`; una fila por `(par, rol)` |
| 6–8 | `advantage` + IC | §5.3, margen esperado bajo el modelo del rol |
| 9 | `n_responses` | Respuestas a ese par concreto en ese rol |
| 10 | `support` | Umbrales de Fuerza de línea (§4.4) |
| 11 | `is_observed` | `n_responses > 0` |
| 12 | `patch_window` | Parámetro de la corrida |

### 6.3 `duo_features_v<patch>.csv` — 18 columnas

| Columnas | Contenido | Cómo se calcula |
|---|---|---|
| 1–5 | Identificación de la dupla y contexto | Orden canónico `a_id < b_id` |
| 6–11 | `synergy` + IC + `_n` + `_support` + `_is_observed` | §5.5; centrado dentro del contexto |
| 12–17 | `lane_strength` + IC + `_n` + `_support` + `_is_observed` | §5.4; sólo `duo_ctx = 'bot'`, vacío en el resto |
| 18 | `patch_window` | Parámetro de la corrida |

---

## 7. Casos límite

| Situación | Qué hace el pipeline |
|---|---|
| **Grafo desconectado** en una dimensión | Se ajusta **una corrida por componente**, cada una centrada en 0 sobre su propia componente. Todos los campeones fuera de la componente mayor se marcan `insufficient` sin importar su `_n`, y el Informe de Calidad de Datos lista las componentes. No se inventa un orden global ([ADR-008](13-adr/ADR-008-conectividad-por-componentes.md), CA-403) |
| Campeón con **una sola comparación** | Se estima: `ε` mantiene el valor finito y lo encoge hacia 0. Sale con `support = insufficient` |
| Campeón **sin ninguna respuesta** en una magnitud | Celda vacía, `_n = 0`, `_support = insufficient` (CA-405) |
| **Todas las respuestas de un par son `even`** | Se ajusta normalmente: `δ ≈ 0` y `τ₁` crece. Es señal legítima de matchup equilibrado (20 §4.3) |
| Dimensión con **más del 40 % de `unknown`** en un par | Entra igual; la tasa se publica en `D_unknown_rate`. Es el sampler quien desprioriza ese par, no el estimador |
| Campeón **desactivado** a mitad de la ventana | Sus respuestas se agregan igual. Aparece en el CSV si sigue en el pool del export |
| Dimensión o atributo **desactivado** a mitad de la ventana | La columna se calcula sobre las respuestas donde estaba activo, y `_n` lo refleja (20 §6) |
| **Menos de 2 campeones** con valor en una dimensión | `_norm` queda vacía en toda la columna: un min-max sobre un punto no significa nada |
| Contexto de dupla **sin ninguna respuesta** | No se emite ninguna fila de ese contexto. No se predice sobre un modelo que no se ajustó |
| Más del **5 % de remuestreos descartados** por desconexión | La dimensión entera se marca `insufficient` y se reporta (§4.2) |
| **Ninguna respuesta pasa los filtros** | La corrida falla con error explícito y **no escribe archivos**. Un CSV con 0 filas y un SHA-256 registrado sería peor que no tener corrida |

---

## 8. La corrida

### 8.1 Interfaz de línea de comandos

```
python -m aggregation.run \
    --patch-window 16.18..16.20 \
    --min-trust     0.30 \
    --halflife      21 \
    --sigma         7.5 \
    --bootstrap     2000 \
    --exported-at   2026-11-10 \
    --out           exports/
```

Todo parámetro omitido se toma de `app_settings` (§9), y el valor **efectivamente usado** —no el
default— es el que se registra.

`--exported-at` es un parámetro y no `now()` por una razón concreta: la fecha entra en la columna
`exported_at` de cada fila, así que sin ella una reproducción hecha otro día daría otro archivo y
CA-408 sería imposible de cumplir. Su default es la fecha de hoy; reproducir una corrida vieja
exige pasar la fecha registrada.

### 8.2 Los ocho pasos

1. Resolver parámetros (CLI → `app_settings` → default) y derivar la semilla (§4.2).
2. Cargar el conjunto filtrado (§1.1) y calcular el peso de cada fila (§2.1).
3. Verificar conectividad por dimensión y por rol; registrar las componentes.
4. Ajustar los cinco estimadores (§5). Los **15 ajustes** —8 dimensiones, 3 roles del 1v1, el 2v2 de
   bot y los 3 contextos de sinergia— son independientes entre sí y corren en paralelo.
5. Bootstrap, con la misma partición de trabajo (§4.2).
6. Centrar, derivar `power_at_*` y `synergy_mean`, calcular `_n`, anchos y `_support`.
7. Escribir los tres CSV con el formato fijo de §4.6 y el Informe de Calidad de Datos.
8. Insertar una fila en `exports` por archivo, con su SHA-256 y **todos** los parámetros.

### 8.3 Qué hace falta para que sea reproducible

CA-408 pide que dos corridas con los mismos parámetros sobre el mismo crudo den un SHA-256 idéntico.
Eso se sostiene sobre cinco cosas, todas fijadas arriba: orden determinista de la consulta base
(§1.1), semilla derivada de los parámetros (§4.2), formato numérico fijo (§4.6), orden de filas fijo
(§4.6) y `exported_at` como parámetro (§8.1). Cualquiera que se afloje rompe la propiedad en
silencio, así que el test de CA-408 corre la misma exportación dos veces y compara hashes.

---

## 9. Parámetros

Todos bajo el prefijo `aggregation.` en `app_settings` (RF-606), salvo `export.min_trust` que ya
existe en [`22-calidad-de-datos.md`](22-calidad-de-datos.md) §8.

| Clave | Inicial | Qué controla |
|---|---|---|
| `aggregation.decay_halflife_days` | `21` | Vida media del decaimiento por recencia (§2.1) |
| `aggregation.bootstrap_samples` | `2000` | Remuestreos del bootstrap (§4.2) |
| `aggregation.power_sigma` | `7.5` | Ancho de la curva de poder (§5.2) |
| `aggregation.bt_prior` | `0.5` | El `ε` de estabilidad numérica (§5.1) |
| `aggregation.duo_lambda_champion` | `0.10` | Penalización L2 sobre `a_·` (§5.4) |
| `aggregation.duo_lambda_interaction` | `1.00` | Penalización L2 sobre `i_··` (§5.4) |
| `aggregation.max_iter` | `500` | Tope de iteraciones del ajuste |
| `aggregation.tol` | `1e-9` | Criterio de convergencia |
| `aggregation.support_thresholds` | tabla de 26 §2.4 | Umbrales de `_support` |
| `aggregation.segment_min_respondents` | `15` | Piso para reportar un segmento (§3.5) |
| `aggregation.segment_min_comparisons` | `300` | Ídem |

Los cuatro primeros y los umbrales se **calibran con los datos del piloto** antes de la entrega
final. Ninguno es una constante del código, y el valor de cada corrida queda registrado.

---

## 10. Complejidad y presupuesto de cómputo

| Etapa | Complejidad | Con el pool de tier 1 |
|---|---|---|
| Carga y ponderación | `O(R)` | ~15 000 filas: segundos |
| Un ajuste de Bradley-Terry | `O(iter · E)`, `E` = pares con al menos una comparación | 780 pares × ~50 iteraciones: milisegundos |
| Bootstrap de una dimensión | `B ·` lo anterior | 2 000 × milisegundos ≈ decenas de segundos |
| Corrida completa | 15 ajustes: 8 dimensiones + 3 roles + 2v2 de bot + 3 contextos | Minutos, con los 15 en paralelo |

El costo dominante es el bootstrap, y es vergonzosamente paralelo. No hay presupuesto de latencia:
la agregación es un trabajo por lotes que dispara el administrador (RF-403), no un endpoint. Los
únicos presupuestos duros del sistema —RNF-01 y RNF-02— son de la ruta de respuesta y este pipeline
no la toca.

---

## 11. Verificación

| Qué se prueba | Cómo | CA |
|---|---|---|
| El orden que produce el modelo es coherente | A le gana a B y B a C ⇒ `θ_A > θ_B > θ_C` | CA-401 |
| El trust pondera | Dos conjuntos idénticos salvo trust dan scores distintos en la dirección esperada | CA-402 |
| **El rango declarado no pondera** | Dos conjuntos idénticos salvo `declared_rank` dan **exactamente** el mismo CSV, hash incluido | §3.2 |
| Grafo desconectado, reportado y no forzado | Dos componentes ⇒ ambas marcadas `insufficient`, sin orden global | CA-403 |
| Toda estimación lleva incertidumbre | Recorrido del CSV: existen `_ci_low ≤ valor ≤ _ci_high`, `_n`, `_support` | CA-404 |
| Vacío no es cero | Campeón sin datos ⇒ celda vacía, `_n = 0`, `insufficient` | CA-405 |
| Observado y predicho se distinguen | Par nunca preguntado ⇒ `is_observed = false`, `n = 0`, IC más ancho | CA-406 |
| La exportación es trazable | Una fila en `exports` por archivo con todos los parámetros | CA-407 |
| Reproducible bit a bit | La misma corrida dos veces ⇒ el mismo SHA-256 | CA-408 |
| La ventana se respeta | Ventana `16.19..16.20` excluye 16.18 y pesa 16.19 menos que 16.20 | CA-409 |
| Honeypots y retests no entran | Agregar un honeypot respondido no cambia ninguna celda | §1.3 |
| La curva es recalculable | `power_at_15` == `exp(−(15−peak)²/(2σ²))` con el `peak` de la misma fila | §5.2 |
| Wilson usa `n_eff` | Con pesos desiguales, el intervalo es más ancho que el calculado con `n` | §5.6 |
| La cabecera es la del fixture | Comparación columna por columna contra [`examples/`](examples/) | 26 §1 |

---

## 12. Precisiones sobre documentos ya en v1

Escribir este documento obligó a resolver cinco cosas que los documentos previos dejaban
subdeterminadas o inconsistentes. Ninguna contradice una decisión cerrada; las cinco deberían
quedar anotadas donde corresponde.

| # | Qué | Dónde impacta | Estado |
|---|---|---|---|
| 1 | La dupla se sigue tomando como competidor, pero su fuerza se parametriza como `a_A + a_B + i_AB`. **Sin esto no existen las filas predichas** que 26 §5 y 20 §5 ya prometen | 20 §5, 26 §5 | Precisión, no cambio. Anotar en ambos |
| 2 | El tipo 4 usa Rao-Kupper de un umbral, no Bradley-Terry sin empates: `similar` es un dato | 20 §5 | Precisión. Anotar |
| 3 | `exports` no tiene dónde guardar `power_sigma` ni los umbrales de `_support`, y 26 §2.4 y §3.3 dicen que quedan registrados ahí | 11 §3.11 | **Falta una columna `params jsonb`.** Requiere migración |
| 4 | `declared_main_role` es `lane_role`, que no tiene valor `fill`, pero `/start` ofrece el botón *Fill*. Hoy un *fill* se guardaría como `NULL` y sería indistinguible de quien omitió | 11 §3.7, 30 §4 | **Inconsistencia.** O se saca el botón, o `declared_main_role` pasa a `text` con su propio `CHECK` |
| 5 | El bootstrap sobre comparaciones subestima la incertidumbre; el criterio y la fecha para decidir si se cambia están en §4.7 | 26 §3.2 | Límite declarado, con disparador |

---

Ver el índice en [`README.md`](README.md) y las decisiones ya cerradas en [`13-adr/`](13-adr/).
