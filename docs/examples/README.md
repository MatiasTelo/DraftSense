# Ejemplos de salida — diccionario de columnas

> Estado: **v1** · Última revisión: 01/09/2026

Los tres archivos de esta carpeta son **ejemplos ejecutables** del contrato de entrega definido en
[`../26-esquema-de-salida.md`](../26-esquema-de-salida.md). Sirven para tres cosas:

1. Mostrarle al Laboratorio DHARMa exactamente qué forma tiene lo que va a recibir, antes de que
   exista una sola respuesta real.
2. Ser el *fixture* de los tests de exportación: un test compara el archivo generado por el pipeline
   contra estos encabezados, columna por columna.
3. Documentar cada columna en un solo lugar, sin tener que leer el pipeline.

> ⚠️ **Los valores son sintéticos.** Ningún número de estos archivos fue medido: son plausibles para
> que el ejemplo se lea bien, y nada más. Lo que **sí es real** es la estructura: el orden y la
> cantidad de columnas, el formato de cada celda, la fórmula de la curva de poder, el intervalo de
> Wilson y los umbrales de `support_level` de [`../26-esquema-de-salida.md`](../26-esquema-de-salida.md) §2.4,
> que están aplicados de verdad sobre los `_n` y los anchos de intervalo de cada fila.

| Archivo | Filas | Columnas |
|---|---|---|
| [`champion_features_v16.20.csv`](champion_features_v16.20.csv) | 13 campeones | 126 |
| [`matchup_matrix_v16.20.csv`](matchup_matrix_v16.20.csv) | 13 pares | 12 |
| [`duo_features_v16.20.csv`](duo_features_v16.20.csv) | 10 duplas | 18 |

El catálogo de ejemplo son 13 campeones elegidos para cubrir los casos borde: un tanque support
(Alistar), un campeón de escalado extremo (Kayle), un jungla (Sejuani, sin fuerza de línea), una
dupla de bot completa (Lucian + Nami), un campeón de tier 2 con poco soporte (Ziggs) y uno de
tier 3 casi sin datos (Ivern), que es el que muestra cómo se ve una fila vacía.

---

## 1. Convenciones que aplican a los tres archivos

### 1.1 El bloque de sufijos

Cada **magnitud medida** ocupa varias columnas, no una. El patrón es siempre el mismo:

| Sufijo | Qué es | Ejemplo |
|---|---|---|
| *(ninguno)* | El valor estimado | `engage` = `1.420` |
| `_ci_low` | Extremo inferior del IC 95 % | `engage_ci_low` = `1.259` |
| `_ci_high` | Extremo superior del IC 95 % | `engage_ci_high` = `1.581` |
| `_n` | Soporte muestral: cuántas observaciones sostienen el valor | `engage_n` = `148` |
| `_support` | `solid` / `limited` / `insufficient`, derivado de `_n` y del ancho | `engage_support` = `solid` |

Leer sólo la columna del valor e ignorar el resto es el error de uso más probable de estos archivos.
Un `engage = 1.42` con `engage_support = insufficient` no es una medición: es un valor con el que no
se puede hacer nada todavía.

### 1.2 Vacío no es cero

Una celda vacía (`,,` en el CSV, `NaN` al leerlo con pandas) significa **"no hay datos"**. Un `0.000`
significa **"el promedio del pool"**, porque los scores están centrados en 0. Confundirlas metería
ruido sistemático en cualquier modelo.

Cuando una celda de valor está vacía, su `_ci_low` y `_ci_high` también lo están, su `_n` es `0` y su
`_support` es `insufficient`. En el ejemplo, la fila de **Ivern** tiene seis de las ocho dimensiones
vacías; la de **Alistar** tiene los tres `lane_strength_*` vacíos porque juega support.

### 1.3 Cómo verificarlo rápido

```python
import pandas as pd

champs = pd.read_csv("champion_features_v16.20.csv")
assert champs.shape[1] == 126

# El contrato del bloque de sufijos: si el valor está vacío, el soporte es insufficient
vacios = champs["engage"].isna()
assert (champs.loc[vacios, "engage_n"] == 0).all()
assert (champs.loc[vacios, "engage_support"] == "insufficient").all()

# El intervalo contiene al valor
ok = champs["engage"].notna()
assert (champs.loc[ok, "engage_ci_low"] <= champs.loc[ok, "engage"]).all()
assert (champs.loc[ok, "engage"] <= champs.loc[ok, "engage_ci_high"]).all()
```

---

## 2. `champion_features_v16.20.csv` — 126 columnas

Una fila por campeón. **20 magnitudes medidas**: 8 dimensiones + 1 pico de poder + 3 fuerzas de
línea + 1 sinergia media + 7 atributos.

### 2.1 Identificación — columnas 1 a 7

| # | Columna | Tipo | Qué es |
|---|---|---|---|
| 1 | `champion_id` | int | Clave interna de DraftSense. Estable entre parches; es la que usan las otras dos tablas para referirse a este campeón |
| 2 | `riot_key` | text | Clave de Data Dragon: `Alistar`, `LeeSin`, `MonkeyKing`. Es la que sirve para cruzar con cualquier fuente externa |
| 3 | `display_name` | text | Nombre tal como se muestra: `Alistar`, `Lee Sin`, `Wukong`. Sólo para leer, nunca para cruzar |
| 4 | `roles` | text | Roles que ocupa el campeón, separados por `\|`: `top\|mid`. Sale del catálogo, no de las respuestas |
| 5 | `pool_tier` | int | `1` núcleo (~40 campeones), `2` expansión (~80), `3` el resto. Un tier alto explica un soporte bajo: se preguntó menos por diseño ([ADR-006](../13-adr/ADR-006-pool-escalonado-por-pick-rate.md)) |
| 6 | `patch_window` | text | Parches cuyas respuestas entraron, en formato `16.18..16.20`. **No** es "el parche del campeón": es la ventana de la corrida |
| 7 | `exported_at` | date | Fecha de la corrida que produjo el archivo |

### 2.2 Dimensiones funcionales — columnas 8 a 63 (8 × 7)

Origen: preguntas de **tipo 1** (comparación pareada). Se ajusta un Bradley-Terry independiente por
dimensión, ponderado por trust y por recencia.

Las 8 dimensiones, en orden: `engage`, `poke`, `pick`, `peel`, `mobility`, `scaling`, `cc`,
`waveclear`.

Por cada dimensión `D`, **siete** columnas:

| Columna | Unidad | Qué es |
|---|---|---|
| `D` | log-odds | Score de Bradley-Terry, **centrado en 0 sobre el pool exportado**. Una diferencia de `+1` entre dos campeones significa que la comunidad elige al primero con probabilidad ≈ 0.73 |
| `D_ci_low`, `D_ci_high` | log-odds | IC 95 % por bootstrap sobre las comparaciones |
| `D_n` | conteo | **Comparaciones que involucran a este campeón en esta dimensión**, no respuestas a un par concreto. Es la unidad correcta: Bradley-Terry estima la fuerza de un campeón con todas sus comparaciones, vengan del par que vengan |
| `D_support` | enum | `solid` si `n ≥ 25` y ancho `≤ 0.60`; `limited` si `n ≥ 10` y ancho `≤ 1.20`; si no, `insufficient` |
| `D_unknown_rate` | 0–1 | Proporción de respuestas `unknown` en los pares que involucran al campeón |
| `D_norm` | 0–1 | `D` reescalado min-max **dentro de este export**. Sólo conveniencia |

Dos columnas piden atención:

**`D_unknown_rate` es señal de validez, no de ruido.** En el ejemplo, `Alistar.waveclear_unknown_rate`
= `0.34`: una de cada tres personas contestó "no sé" cuando se le preguntó por el waveclear de un
tanque support. Lo más probable no es que estuvieran distraídas, sino que **la dimensión no aplica
bien a ese campeón**. Es información útil para decidir qué columnas son informativas para qué
campeones — y por eso se exporta en vez de descartarse.

**⚠️ `D_norm` no es comparable entre exports.** Su referencia son el mínimo y el máximo del pool de
*esta* corrida, que cambian cuando se promueven campeones de tier. Para comparar entre parches hay
que usar la columna en log-odds. En el ejemplo, `Alistar.engage_norm` = `1.000` sólo quiere decir
"es el que más engage tiene **de estos 13**".

### 2.3 Pico de poder — columnas 64 a 73

Origen: preguntas de **tipo 2** (slider de minuto). Mediana ponderada con IC por bootstrap.

| Columna | Unidad | Qué es |
|---|---|---|
| `peak_minute` | minutos | Mediana ponderada del minuto de pico declarado, entero en 0–40 |
| `peak_minute_ci_low`, `peak_minute_ci_high` | minutos | IC 95 % bootstrap, en minutos enteros |
| `peak_minute_n` | conteo | Respuestas de tipo 2 sobre este campeón |
| `peak_minute_support` | enum | `solid` si `n ≥ 20` y ancho `≤ 4 min`; `limited` si `n ≥ 10` y ancho `≤ 8 min` |
| `power_at_5` … `power_at_25` | 0–1 | La curva de poder evaluada en los minutos 5, 10, 15, 20 y 25 |

Las cinco `power_at_*` **no son cinco mediciones nuevas**: son una transformación determinista de
`peak_minute`.

```
power_at(t) = exp( -(t - peak_minute)² / (2 · σ²) )        con σ = 7.5
```

Vale exactamente `1` en el pico y decae simétricamente hacia ambos lados. Se eligió una campana y no
una rampa con meseta porque la rampa afirmaría que un campeón de *early game* conserva su poder
máximo en el minuto 40 ([ADR-009](../13-adr/ADR-009-curva-de-poder-gaussiana.md)). Se incluyen ya
calculadas para que el laboratorio no tenga que elegir su propia `σ`, que es lo que haría que dos
análisis dejaran de ser comparables. El valor de `σ` usado queda registrado en la tabla `exports`.

En el ejemplo se ve el contraste que la columna existe para capturar:

| Campeón | `peak_minute` | `power_at_5` | `power_at_15` | `power_at_25` |
|---|---|---|---|---|
| Darius | 12 | 0.65 | 0.92 | 0.22 |
| Alistar | 14 | 0.49 | 0.99 | 0.34 |
| Kayle | 31 | 0.00 | 0.10 | 0.73 |

### 2.4 Fuerza de línea — columnas 74 a 88 (3 × 5)

Origen: preguntas de **tipo 3, variante 1v1**. Bradley-Terry con empates y margen (Rao-Kupper),
ajustado por rol.

Por cada rol `R` ∈ {`top`, `mid`, `adc`}:

| Columna | Unidad | Qué es |
|---|---|---|
| `lane_strength_R` | log-odds | Fuerza en el 1v1 de línea al minuto 10, centrada en 0 **dentro de ese rol** |
| `lane_strength_R_ci_low`, `_ci_high` | log-odds | IC 95 % bootstrap |
| `lane_strength_R_n` | conteo | Comparaciones del campeón en ese rol |
| `lane_strength_R_support` | enum | `solid` si `n ≥ 20` y ancho `≤ 0.60`; `limited` si `n ≥ 8` y ancho `≤ 1.20` |

**Sólo hay tres roles**, y falta cada uno por una razón distinta:

- **`jungle` no existe** porque un jungla no disputa un 1v1 de línea: no tiene oponente fijo con
  quien intercambiar durante diez minutos, así que la pregunta no tendría respuesta clara. Sejuani,
  en el ejemplo, tiene los tres vacíos y queda caracterizada por las 8 dimensiones.
- **`support` no existe** porque el carril inferior sí se mide, pero **la unidad es la dupla**. Vive
  en `duo_features.csv` como `lane_strength`. Alistar y Nami tienen los tres vacíos.

Un campeón con dos roles los tiene ambos, con soportes distintos: Kayle tiene
`lane_strength_top_n = 41` (`solid`) y `lane_strength_mid_n = 14` (`limited`), que es exactamente lo
que se espera de un campeón que se juega mucho más en una línea que en la otra.

### 2.5 Sinergia media — columnas 89 a 91

Origen: preguntas de **tipo 4**. Bradley-Terry sobre duplas.

| Columna | Unidad | Qué es |
|---|---|---|
| `synergy_mean` | log-odds | Sinergia promedio del campeón con **todas** las parejas evaluadas |
| `synergy_mean_n` | conteo | Duplas distintas que lo incluyen y tienen al menos una respuesta |
| `synergy_mean_support` | enum | `solid` si `n ≥ 15` y ancho `≤ 0.80`; `limited` si `n ≥ 6` y ancho `≤ 1.50` |

**Es la única magnitud del archivo sin `_ci_low` / `_ci_high`, y es deliberado.** No es una
estimación del modelo: es un **resumen derivado**, el promedio de estimaciones que ya tienen su
propio intervalo en `duo_features.csv`. Un IC honesto para ese promedio exigiría propagar la
covarianza entre duplas que comparten un campeón, que es justamente la estructura que el promedio
borra. Sirve para responder *"¿este campeón es fácil de acompañar en general?"*; **para elegir una
dupla hay que ir a `duo_features.csv`**, donde el dato es pareado y sí tiene intervalo.

### 2.6 Atributos — columnas 92 a 126 (7 × 5)

Origen: preguntas de **tipo 5** (multi-selección). Proporción ponderada con intervalo de Wilson.

Los 7 atributos, en orden: `engage`, `poke`, `pick`, `peel`, `front_to_back`, `dive`, `split_push`.

Por cada atributo `T`:

| Columna | Unidad | Qué es |
|---|---|---|
| `trait_T` | 0–1 | Proporción ponderada de respondedores que marcaron el atributo para este campeón |
| `trait_T_ci_low`, `trait_T_ci_high` | 0–1 | Intervalo de **Wilson** al 95 % |
| `trait_T_n` | conteo | Respuestas de tipo 5 sobre este campeón |
| `trait_T_support` | enum | `solid` si `n ≥ 20` y ancho de Wilson `≤ 0.25`; `limited` si `n ≥ 10` y ancho `≤ 0.45` |

**Los siete `trait_T_n` de una misma fila son idénticos.** Una respuesta de tipo 5 marca los siete
atributos de una sola vez, así que el soporte es por campeón, no por atributo. Si en algún export
difieren, hay un bug en la agregación.

**Por qué Wilson y no el intervalo normal:** con muestras chicas y proporciones cerca de 0 o de 1 —
que es exactamente el caso de un atributo que casi nadie o casi todos marcan — el intervalo normal
produce extremos fuera de `[0,1]`. En el ejemplo, `Kayle.trait_engage` = `0.040` con n = 52 da
Wilson `[0.011, 0.132]`; el normal daría un extremo inferior negativo.

**⚠️ `trait_engage` no es `engage`.** Cuatro atributos se llaman igual que cuatro dimensiones y son
mediciones distintas y no intercambiables:

| | `engage` (dimensión) | `trait_engage` (atributo) |
|---|---|---|
| Pregunta que responde | ¿cuánto engage tiene **comparado con los demás**? | ¿qué fracción de la comunidad dice que **hace** engage? |
| Escala | log-odds, sin cero natural | proporción 0–1, con cero y uno naturales |
| Origen | tipo 1 | tipo 5 |

Un campeón puede tener `engage = -0.40` y `trait_engage = 0.71` sin contradicción: está por debajo
de la media del pool y aun así la mayoría reconoce que hace engage. Por eso los nombres nunca
colisionan en el CSV.

**Estas 7 columnas son el puente de retrocompatibilidad**: son las mismas 7 etiquetas binarias del
esquema manual actual, sobre la misma definición, pero como proporción continua con incertidumbre en
vez de un binario de un solo anotador. Sin ellas, cualquier mejora del modelo del laboratorio sería
inatribuible.

---

## 3. `matchup_matrix_v16.20.csv` — 12 columnas

Una fila por par de campeones que compiten en el mismo rol. Origen: **tipo 3, variante 1v1**.

| # | Columna | Tipo | Qué es |
|---|---|---|---|
| 1–2 | `champion_a_id`, `champion_a_key` | int, text | Campeón A |
| 3–4 | `champion_b_id`, `champion_b_key` | int, text | Campeón B. **Siempre `a_id < b_id`** |
| 5 | `role` | text | `top` / `mid` / `adc` |
| 6 | `advantage` | −1 … +1 | Ventaja de **A sobre B** en el 1v1 al minuto 10. Positivo = gana A |
| 7–8 | `advantage_ci_low`, `advantage_ci_high` | −1 … +1 | IC 95 % |
| 9 | `n_responses` | conteo | Respuestas observadas **para este par concreto** |
| 10 | `support` | enum | Ver §2.4 de `26-esquema-de-salida.md` |
| 11 | `is_observed` | bool | `true` si el par se preguntó; `false` si el valor lo predijo el modelo |
| 12 | `patch_window` | text | Parches incluidos |

### La matriz es antisimétrica

`advantage(B, A) = −advantage(A, B)`. Se almacena **una sola dirección** para no duplicar filas ni
invitar a inconsistencias. Para consultar en cualquier dirección:

```python
mus = pd.read_csv("matchup_matrix_v16.20.csv")

def ventaja(a, b, role):
    fila = mus[(mus.role == role) &
               (((mus.champion_a_key == a) & (mus.champion_b_key == b)) |
                ((mus.champion_a_key == b) & (mus.champion_b_key == a)))]
    if fila.empty:
        return None
    f = fila.iloc[0]
    return f.advantage if f.champion_a_key == a else -f.advantage
```

### `is_observed` es la columna más importante del archivo

Con el pool inicial hay cientos de pares posibles por rol y sólo una fracción llega a preguntarse.
Bradley-Terry rellena el resto — para eso se eligió, estima a partir de comparaciones parciales —
pero **un valor predicho no es evidencia recolectada**.

En el ejemplo, comparar las dos últimas filas con el resto:

| Par | `n_responses` | Ancho del IC | `is_observed` |
|---|---|---|---|
| Jhin vs Lucian (adc) | 31 | 0.40 | `true` |
| Darius vs Garen (top) | 41 | 0.34 | `true` |
| Karma vs Kayle (mid) | 0 | **1.24** | `false` |
| Lucian vs Zed (mid) | 0 | **1.24** | `false` |

Las filas predichas tienen `n_responses = 0` y un intervalo notoriamente más ancho. Filtrar por
`is_observed` es la forma de quedarse sólo con evidencia:

```python
observados = mus[mus.is_observed]
```

Los cinco niveles de la respuesta se mapean a `{a_strong: +1, a_slight: +0.5, even: 0,
b_slight: −0.5, b_strong: −1}` antes del ajuste.

---

## 4. `duo_features_v16.20.csv` — 18 columnas

Una fila por dupla evaluada, con **dos magnitudes independientes** que responden preguntas distintas.

| # | Columna | Tipo | Qué es |
|---|---|---|---|
| 1–2 | `champion_a_id`, `champion_a_key` | int, text | Campeón A |
| 3–4 | `champion_b_id`, `champion_b_key` | int, text | Campeón B. **Siempre `a_id < b_id`** |
| 5 | `duo_context` | text | `bot` / `top_jungle` / `mid_jungle` — dónde actúan juntos |
| 6 | `synergy` | log-odds | **¿Estos dos se complementan bien?** Compenetración de la dupla, centrada en 0. Origen: tipo 4 |
| 7–8 | `synergy_ci_low`, `synergy_ci_high` | log-odds | IC 95 % |
| 9 | `synergy_n` | conteo | Comparaciones de tipo 4 que incluyeron esta dupla |
| 10 | `synergy_support` | enum | `solid` si `n ≥ 15` y ancho `≤ 0.80`; `limited` si `n ≥ 6` y ancho `≤ 1.50` |
| 11 | `synergy_is_observed` | bool | `true` si la dupla se preguntó; `false` si es predicha |
| 12 | `lane_strength` | log-odds | **¿Esta dupla le gana el carril a otra?** Fuerza en el 2v2 de bot, centrada en 0. Origen: tipo 3, variante 2v2 |
| 13–14 | `lane_strength_ci_low`, `lane_strength_ci_high` | log-odds | IC 95 % |
| 15 | `lane_strength_n` | conteo | Comparaciones de tipo 3 2v2 que incluyeron esta dupla |
| 16 | `lane_strength_support` | enum | Mismos umbrales que `synergy` |
| 17 | `lane_strength_is_observed` | bool | `true` si la dupla se preguntó; `false` si es predicha |
| 18 | `patch_window` | text | Parches incluidos |

### Las dos magnitudes no son redundantes

Una dupla puede tener sinergia altísima y perder el carril igual contra una dupla que la
contrarresta; y al revés, dos campeones que no se complementan especialmente pueden ganar el carril
por fuerza bruta individual. En el ejemplo:

| Dupla | `synergy` | `lane_strength` | Lectura |
|---|---|---|---|
| Lucian + Nami | `1.120` | `0.860` | Se complementan **y** ganan el carril |
| Jhin + Karma | `0.240` | `-0.350` | Se complementan razonablemente pero **pierden** el carril |

Por eso se recolectan por separado, con dos tipos de pregunta distintos.

### `lane_strength` sólo tiene valor en `bot`

El enfrentamiento 2v2 se pregunta únicamente sobre el carril inferior, que es donde dos campeones
comparten oponentes durante toda la fase de líneas. Para `top_jungle` y `mid_jungle` la columna queda
**vacía**, con `_n = 0`, `_support = insufficient` y `_is_observed = false`: sólo se mide `synergy`.
En el ejemplo, las filas de Sejuani con Darius, Garen, Syndra y Zed.

### Ambas magnitudes son simétricas

Acompañar a A con B es lo mismo que acompañar a B con A, así que se guarda una sola forma canónica
(`a_id < b_id`), igual que en la matriz de matchups. **No hay antisimetría acá**: a diferencia de
`advantage`, no se cambia el signo al invertir el orden.

### Es el archivo de soporte más flojo de los tres

El espacio de duplas es el cuadrado del de campeones, y los tipos 4 y 3-2v2 suman apenas el 10 % de
la mezcla de preguntas — su prioridad es deliberadamente menor que la de los tipos 1, 2 y 3. En el
ejemplo **no hay una sola celda `solid`**, y eso es fiel a lo que se espera del piloto. Esperar
menos precisión acá es parte del diseño, no una falla.

### Por qué no hay una matriz de dupla contra dupla

El tipo 3 en su variante 2v2 recolecta enfrentamientos entre duplas concretas, así que podría
emitirse una matriz `dupla × dupla`. **No se emite**: el espacio de pares de duplas es el cuadrado
del de duplas, y con el volumen del piloto ese archivo sería casi enteramente predicciones del
modelo — un archivo grande con casi nada de evidencia adentro. La ventaja de una dupla sobre otra se
deriva de la diferencia de sus `lane_strength`, en una línea de código.

---

## 5. Trazabilidad

Cada archivo real queda registrado en la tabla `exports` con `sha256`, `row_count`, `column_count`,
`responses_included`, `respondents_included`, `min_trust_applied`, `patch_window`,
`decay_halflife_days`, `bootstrap_samples`, `aggregation_version` y `created_at`.

Con esos parámetros y la tabla `responses` —que es append-only— cualquier corrida se reproduce bit a
bit. Si un resultado del laboratorio resulta sorprendente, se puede reconstruir exactamente el
archivo que lo produjo.

---

## 6. Cómo se regeneran estos ejemplos

```
python scripts/build_example_exports.py draftsense/docs/examples
```

El script no toca la base: arma los tres archivos desde una tabla de valores sintéticos, pero
**calcula de verdad** los intervalos de Wilson, la curva de poder y los `support_level`, y verifica
con `assert` que las tres cabeceras tengan 126, 12 y 18 columnas. Si alguien cambia el esquema de
salida sin actualizar el script, falla.
