# 26 — Esquema de salida

> Estado: **v2** · Última revisión: 08/10/2026
>
> **v2 (08/10/2026):** `champion_features` se divide en cuatro archivos en formato largo, se
> elimina `synergy_mean` y `duo_context` pasa a `role_a` y `role_b`
> ([ADR-023](13-adr/ADR-023-salida-en-formato-largo.md)). Es la corrección pedida en la reunión
> del 05/10/2026 con el tutor de la organización.

Define exactamente qué archivos recibe el Laboratorio DHARMa y qué contiene cada columna: nombre,
fórmula, rango, unidad y origen. Es el **contrato de entrega** de la práctica: lo que está acá es
lo que el laboratorio puede esperar.

---

## 1. Los siete archivos

Cada corrida del pipeline emite siete archivos, versionados por ventana de parches:

| Archivo | Granularidad | Filas esperadas |
|---|---|---|
| `champion_dimensions_v<patch>.csv` | una fila por (campeón, dimensión) | 8 por campeón: 320 (tier 1) a 1 360 |
| `peak_timing_v<patch>.csv` | una fila por campeón | 40 a 170 |
| `champion_lane_strength_v<patch>.csv` | una fila por (campeón, rol) | 3 por campeón: 120 a 510 |
| `champion_traits_v<patch>.csv` | una fila por (campeón, atributo) | 7 por campeón: 280 a 1 190 |
| `matchup_matrix_v<patch>.csv` | una fila por (campeón A, campeón B, rol) | ~300 – 2 000 |
| `duo_features_v<patch>.csv` | una fila por (campeón A, campeón B, rol de A, rol de B) | ~200 – 1 500 |
| `data_quality_report_v<patch>.md` | — | ver [`27-validacion-confiabilidad.md`](27-validacion-confiabilidad.md) |

Los seis CSV corresponden a **tres granularidades**: el campeón (los cuatro primeros, uno por tipo
de pregunta), el par de campeones que se enfrentan y la dupla de campeones que juegan juntos.
Ninguna medición cae fuera de esas tres.

Cada archivo queda registrado en la tabla `exports` con su SHA-256 y los parámetros exactos de la
corrida que lo produjo, de modo que cualquier entrega es reproducible y verificable.

**Hay un ejemplo ejecutable de los seis CSV en [`examples/`](examples/)**, con un diccionario
columna por columna y las trampas de lectura señaladas. Los valores son sintéticos; la estructura, el
formato de cada celda y los `support_level` son reales. Es además el *fixture* contra el que los
tests de exportación comparan las cabeceras.

**Fuera de alcance:** no se emite ningún archivo a nivel de partida. DraftSense mide campeones; el
análisis de partidas es del laboratorio ([ADR-005](13-adr/ADR-005-alcance-medicion-de-campeones.md)).

---

## 2. Convenciones que aplican a todos los archivos

### 2.1 Nombres de columna

`snake_case`. Cada magnitud medida se acompaña de un bloque fijo de sufijos:

| Sufijo | Significado |
|---|---|
| *(ninguno)* | El valor estimado |
| `_ci_low` / `_ci_high` | Extremos del intervalo de confianza al 95 % |
| `_n` | Soporte muestral: cuántas observaciones sostienen la estimación |
| `_support` | `solid` \| `limited` \| `insufficient` — ver §2.4 |

### 2.2 Dimensión y atributo con el mismo nombre no son lo mismo

Cuatro de los siete atributos del tipo 5 (`engage`, `poke`, `pick`, `peel`) **se llaman igual que
cuatro de las ocho dimensiones del tipo 1**, pero son mediciones distintas y no intercambiables:

- `engage` como **dimensión** es un **score relativo** derivado de comparaciones pareadas: responde
  *"¿cuánto engage tiene este campeón comparado con los demás?"*. Escala log-odds, sin cero natural.
  Vive en `champion_dimensions`, columna `score`.
- `engage` como **atributo** es una **proporción absoluta**: responde *"¿qué fracción de la
  comunidad dice que este campeón hace engage?"*. Escala 0–1, con cero y uno naturales. Vive en
  `champion_traits`, columna `proportion`.

Un campeón puede tener `score = -0.4` en la dimensión `engage` (por debajo de la media del pool) y
`proportion = 0.71` en el atributo `engage` (la mayoría reconoce que hace engage) sin ninguna
contradicción. Mezclarlas al alimentar un modelo sería un error silencioso.

> **Cambiado el 08/10/2026.** En el archivo ancho, el prefijo `trait_` era lo que impedía que los
> nombres colisionaran. Con el formato largo ([ADR-023](13-adr/ADR-023-salida-en-formato-largo.md))
> cada medición vive en su propio archivo y con su propia columna de valor, así que el prefijo dejó
> de hacer falta. La advertencia de fondo sigue en pie.

### 2.3 Valores faltantes

Una celda sin datos se escribe **vacía** (que pandas lee como `NaN`), **nunca como `0`**. La
distinción es crítica: `0` en `score` significa "promedio del pool en esa dimensión"; vacío
significa "no tenemos datos sobre este campeón en esta dimensión". Confundirlas metería ruido
sistemático en el modelo.

Cuando un valor está vacío, su `_n` es `0` y su `_support` es `insufficient`.

### 2.4 `support_level`

Todo se exporta; nada se excluye en silencio. `_support` traduce el soporte muestral y el ancho del
intervalo a un juicio legible, para que el laboratorio filtre con su propio criterio
([ADR-011](13-adr/ADR-011-support-level-en-vez-de-excluir.md)).

| Magnitud | `solid` | `limited` | `insufficient` |
|---|---|---|---|
| Dimensiones (log-odds) | `n ≥ 25` y ancho de IC `≤ 0.60` | `n ≥ 10` y ancho `≤ 1.20` | resto |
| Pico de poder (minutos) | `n ≥ 20` y ancho `≤ 4 min` | `n ≥ 10` y ancho `≤ 8 min` | resto |
| Fuerza de línea (log-odds) | `n ≥ 20` y ancho `≤ 0.60` | `n ≥ 8` y ancho `≤ 1.20` | resto |
| Sinergia (log-odds) | `n ≥ 15` y ancho `≤ 0.80` | `n ≥ 6` y ancho `≤ 1.50` | resto |
| Atributos (proporción) | `n ≥ 20` y ancho de Wilson `≤ 0.25` | `n ≥ 10` y ancho `≤ 0.45` | resto |

Para las dimensiones, `n` cuenta **comparaciones que involucran a ese campeón en esa dimensión**,
no respuestas al par. Es la unidad correcta: Bradley-Terry estima la fuerza de un campeón a partir
de todas sus comparaciones, vengan del par que vengan.

Los umbrales son la primera calibración y se revisan con los datos reales del piloto antes de la
entrega final; el valor usado en cada corrida queda registrado en `exports`.

### 2.5 Escala de los scores de Bradley-Terry

Los scores de las dimensiones, la fuerza de línea y la sinergia se exportan en **log-odds,
centrados en 0 sobre el pool exportado**. Una diferencia de `+1` entre dos campeones significa que
la comunidad elige al primero con probabilidad ≈ 0.73 frente al segundo (`1/(1+e⁻¹)`).

Se eligió esta escala y no una normalización 0–1 porque es la escala en la que el modelo estima y
en la que el intervalo de confianza es simétrico e interpretable. Como conveniencia se agrega una
columna `_norm` con el mismo valor reescalado min-max a `[0,1]` dentro del export (en
`champion_dimensions`, `score_norm`, dentro de cada dimensión).

> ⚠️ **`_norm` no es comparable entre exports.** Su referencia es el mínimo y el máximo del pool de
> esa corrida, que cambia cuando se promueven campeones de tier. Para comparar entre parches hay que
> usar la columna en log-odds. El Informe de Calidad de Datos repite esta advertencia.

### 2.6 Filtro de confianza

Las respuestas de respondedores con `trust_score < 0.30` no entran en la agregación. **Nunca se
borran de `responses`**: el umbral es un parámetro de la corrida y queda registrado en
`exports.min_trust_applied`, de modo que el laboratorio puede pedir un reanálisis con otro umbral.
Las respuestas de respondedores con `is_flagged = true` tampoco entran.

---

## 3. Los cuatro archivos por campeón

> **Cambiado el 08/10/2026** ([ADR-023](13-adr/ADR-023-salida-en-formato-largo.md)), después de la
> reunión del 05/10 con Marinozi. Hasta acá había un único `champion_features_v<patch>.csv`, con una
> fila por campeón y 126 columnas. Ahora son **cuatro archivos en formato largo**, para que el
> laboratorio filtre por dimensión, por rol o por atributo. `synergy_mean` se eliminó.

**19 magnitudes medidas por campeón**: 8 dimensiones, 1 pico de poder, 3 fuerzas de línea y 7
atributos. Comparado con las 7 etiquetas binarias del esquema actual, todas son continuas, todas
tienen intervalo de confianza y soporte muestral, y todas se versionan por parche.

| Archivo | Origen | Filas por campeón | Columnas |
|---|---|---|---|
| `champion_dimensions_v<patch>.csv` | tipo 1 | 8, una por dimensión | 15 |
| `peak_timing_v<patch>.csv` | tipo 2 | 1 | 17 |
| `champion_lane_strength_v<patch>.csv` | tipo 3, variante 1v1 | 3, una por rol | 13 |
| `champion_traits_v<patch>.csv` | tipo 5 | 7, una por atributo | 13 |

### 3.1 Identificación: 7 columnas, en los cuatro archivos

Cada archivo se puede usar solo, así que todos repiten las mismas siete columnas al principio. En
los archivos largos se repiten en cada fila del campeón.

| Columna | Tipo | Contenido |
|---|---|---|
| `champion_id` | int | Clave interna de DraftSense |
| `riot_key` | text | Clave de Data Dragon: `Alistar`, `LeeSin`, `MonkeyKing` |
| `display_name` | text | Nombre mostrado: `Alistar`, `Lee Sin`, `Wukong` |
| `roles` | text | Roles separados por `\|`: `top\|jungle` |
| `pool_tier` | int | 1 núcleo, 2 expansión, 3 resto |
| `patch_window` | text | Parches incluidos: `16.18..16.20` |
| `exported_at` | date | Fecha de la corrida |

### 3.2 `champion_dimensions_v<patch>.csv`: 15 columnas

Origen: **tipo 1**, Bradley-Terry ponderado por trust, una corrida independiente por dimensión. Las
comparaciones salen de los rankings de cinco campeones
([ADR-022](13-adr/ADR-022-tipo-1-ranking-de-cinco.md)): cada ranking aporta diez.

Hay **una fila por (campeón, dimensión)**, así que cada campeón aparece ocho veces, una por cada
`dimension` ∈ {`engage`, `poke`, `pick`, `peel`, `mobility`, `scaling`, `cc`, `waveclear`}. A las 7
de identificación se suman:

| Columna | Unidad | Fórmula / contenido |
|---|---|---|
| `dimension` | text | Código de la dimensión |
| `score` | log-odds | Score de Bradley-Terry, centrado en 0 sobre el pool |
| `score_ci_low`, `score_ci_high` | log-odds | IC 95 % por bootstrap sobre las comparaciones (2 000 remuestreos) |
| `score_n` | conteo | Comparaciones que involucran al campeón en esa dimensión |
| `score_support` | enum | Ver §2.4 |
| `unknown_rate` | 0–1 | Proporción de respuestas `unknown` en los pares que involucran al campeón |
| `score_norm` | 0–1 | `score` reescalado min-max **dentro de la dimensión** y del export. Sólo conveniencia (§2.5) |

**`unknown_rate` es una señal de validez, no de ruido.** Cuando un campeón acumula muchas
respuestas `unknown` en una dimensión, lo más probable es que la dimensión no le aplique bien
—preguntar cuánto *waveclear* tiene un support enchantress no tiene respuesta clara— y no que la
gente esté distraída. El laboratorio puede usarla para decidir qué dimensiones son informativas para
qué campeones.

Un *Not sure* sobre un ranking se registra como `unknown` en sus diez pares (ADR-022), así que entra
en el `unknown_rate` de los cinco campeones del ranking.

### 3.3 `peak_timing_v<patch>.csv`: 17 columnas

Origen: **tipo 2**, mediana ponderada por trust con IC bootstrap. Una fila por campeón. A las 7 de
identificación se suman:

| Columna | Unidad | Contenido |
|---|---|---|
| `peak_minute` | minutos | Mediana ponderada del minuto de pico declarado |
| `peak_minute_ci_low`, `peak_minute_ci_high` | minutos | IC 95 % bootstrap (2 000 remuestreos) |
| `peak_minute_n` | conteo | Respuestas de tipo 2 sobre el campeón |
| `peak_minute_support` | enum | Ver §2.4 |
| `power_at_5`, `power_at_10`, `power_at_15`, `power_at_20`, `power_at_25` | 0–1 | Curva de poder evaluada en cada corte |

**La curva de poder** convierte un único número —el minuto de pico— en un perfil temporal:

```
power_at(t) = exp( -(t - peak_minute)² / (2 · σ²) )
```

`σ` es global, se calibra con los datos del piloto y queda registrada en `exports`. La curva vale 1
exactamente en el pico y decae de forma simétrica hacia los dos lados.

Se eligió una campana y no una rampa creciente con meseta porque la rampa afirmaría que un campeón
de *early game* conserva su poder máximo en el minuto 40. Eso es falso, y borra justamente la señal
que el laboratorio quiere medir: **que un equipo esté fuerte temprano implica que está débil
tarde** ([ADR-009](13-adr/ADR-009-curva-de-poder-gaussiana.md)).

Las cinco columnas `power_at_*` son una **transformación determinista de `peak_minute`**, no cinco
mediciones nuevas. Se incluyen porque así entra la dimensión temporal a un modelo, y calcularlas del
lado del laboratorio invitaría a que cada quien use una `σ` distinta.

### 3.4 `champion_lane_strength_v<patch>.csv`: 13 columnas

Origen: **tipo 3 en su variante 1v1**, Bradley-Terry con empates y margen (modelo Rao-Kupper),
ajustado por rol.

Hay **una fila por (campeón, rol)** y **siempre tres filas por campeón**, una por cada `role` ∈
{`top`, `mid`, `adc`}. A las 7 de identificación se suman:

| Columna | Unidad | Contenido |
|---|---|---|
| `role` | text | `top` \| `mid` \| `adc` |
| `lane_strength` | log-odds | Fuerza en el 1v1 de línea al minuto 10, centrada en 0 |
| `lane_strength_ci_low`, `lane_strength_ci_high` | log-odds | IC 95 % bootstrap |
| `lane_strength_n` | conteo | Comparaciones del campeón en ese rol |
| `lane_strength_support` | enum | Ver §2.4 |

Si el campeón no juega un rol, la fila de ese rol **igual está**: con `lane_strength` vacío,
`lane_strength_n = 0` y `insufficient` (§2.3 y
[ADR-011](13-adr/ADR-011-support-level-en-vez-de-excluir.md)). Sólo hay tres roles a nivel campeón,
y cada exclusión tiene su propia razón:

- **La jungla no disputa un 1v1 de línea.** Un jungla no tiene un oponente fijo con quien
  intercambiar durante diez minutos, así que la pregunta no tiene una respuesta clara. A los junglas
  los caracterizan las 8 dimensiones del tipo 1, que aplican a todos.
- **El carril inferior sí se mide, pero la unidad es la dupla, no el campeón.** El enfrentamiento de
  bot es 2v2 y su resultado es una propiedad conjunta del adc y su support: separarlo en dos números
  individuales sería inventar información. Vive en `duo_features.csv` como `lane_strength`.

El esquema que preveía la Especificación Técnica pedía `matchup_score` para los cinco roles; acá se
corrige.

### 3.5 `champion_traits_v<patch>.csv`: 13 columnas

Origen: **tipo 5**, proporción ponderada por trust con intervalo de Wilson.

Hay **una fila por (campeón, atributo)**, así que cada campeón aparece siete veces, una por cada
`trait` ∈ {`engage`, `poke`, `pick`, `peel`, `front_to_back`, `dive`, `split_push`}. A las 7 de
identificación se suman:

| Columna | Unidad | Contenido |
|---|---|---|
| `trait` | text | Código del atributo |
| `proportion` | 0–1 | Proporción ponderada de respondedores que marcaron el atributo |
| `proportion_ci_low`, `proportion_ci_high` | 0–1 | Intervalo de Wilson al 95 % |
| `proportion_n` | conteo | Respuestas de tipo 5 sobre el campeón |
| `proportion_support` | enum | Ver §2.4 |

**Por qué Wilson y no el intervalo normal.** Con muestras chicas y proporciones cerca de 0 o de 1
—justo el caso de un atributo que casi nadie o casi todos marcan— el intervalo normal da extremos
fuera de `[0,1]`. Wilson no.

**Este archivo es el puente de retrocompatibilidad.** Son las mismas 7 etiquetas del esquema manual
actual, medidas con la misma definición, pero como proporción continua con incertidumbre en vez de
un binario de un solo anotador. Así se puede comparar el modelo nuevo contra el anterior con todo
constante salvo la calidad del etiquetado; sin este archivo, cualquier mejora del modelo sería
inatribuible.

### 3.6 Por qué no hay sinergia media por campeón

Hasta el 07/10 la salida por campeón tenía `synergy_mean`: el promedio de la sinergia de cada campeón con
todas sus parejas. **Se eliminó** a pedido de la organización (ADR-023). La sinergia se mide por
dupla y su único dato útil es el pareado, que vive en `duo_features.csv` (§5).

---

## 4. `matchup_matrix_v<patch>.csv`

Una fila por par de campeones que compiten en el mismo rol. Origen: **tipo 3**.

| Columna | Tipo | Contenido |
|---|---|---|
| `champion_a_id`, `champion_a_key` | int, text | Campeón A. Siempre `a_id < b_id` (forma canónica) |
| `champion_b_id`, `champion_b_key` | int, text | Campeón B |
| `role` | text | `top` \| `mid` \| `adc` |
| `advantage` | −1 … +1 | Ventaja de A sobre B en el 1v1 al minuto 10. Positivo = gana A |
| `advantage_ci_low`, `advantage_ci_high` | −1 … +1 | IC 95 % |
| `n_responses` | conteo | Respuestas observadas **para este par concreto** |
| `support` | enum | Ver §2.4 |
| `is_observed` | bool | `true` si el par se preguntó; `false` si el valor es predicho por el modelo |
| `patch_window` | text | Parches incluidos |

**La matriz es antisimétrica:** `advantage(B, A) = −advantage(A, B)`. Se almacena una sola dirección
para no duplicar filas ni invitar a inconsistencias; la otra se obtiene cambiando el signo.

**`is_observed` es la columna más importante del archivo.** Con el pool inicial hay cientos de pares
posibles por rol y sólo una fracción llega a preguntarse. Bradley-Terry rellena el resto —para eso
se eligió: estima a partir de comparaciones parciales— pero un valor predicho no es evidencia
recolectada, y el laboratorio tiene que poder distinguirlos. Las filas con `is_observed = false`
tienen `n_responses = 0` y un intervalo notoriamente más ancho.

Los cinco niveles de respuesta se mapean a `{a_strong: +1, a_slight: +0.5, even: 0, b_slight: −0.5,
b_strong: −1}` antes del ajuste.

---

## 5. `duo_features_v<patch>.csv`

Una fila por dupla evaluada, con **dos magnitudes independientes** que responden preguntas
distintas:

- **`synergy`** — *¿estos dos se complementan bien?* Origen: **tipo 4**, comparación entre duplas
  sobre su compenetración interna.
- **`lane_strength`** — *¿esta dupla le gana el carril a otra?* Origen: **tipo 3, variante 2v2**,
  enfrentamiento directo entre duplas de bot.

Son cosas diferentes y no redundantes: una dupla puede tener sinergia altísima y perder igual contra
una dupla que la contrarresta, y al revés, dos campeones que no se complementan especialmente pueden
ganar el carril por fuerza bruta individual. Por eso se recolectan por separado.

| Columna | Tipo | Contenido |
|---|---|---|
| `champion_a_id`, `champion_a_key` | int, text | Campeón A. Siempre `a_id < b_id` |
| `champion_b_id`, `champion_b_key` | int, text | Campeón B |
| `role_a` | text | Rol de `champion_a` en la dupla: `adc` \| `support` \| `top` \| `mid` \| `jungle` |
| `role_b` | text | Rol de `champion_b` en la dupla, con los mismos valores |
| `synergy` | log-odds | Compenetración de la dupla, centrada en 0 |
| `synergy_ci_low`, `synergy_ci_high` | log-odds | IC 95 % |
| `synergy_n` | conteo | Comparaciones de tipo 4 que incluyeron esta dupla |
| `synergy_support` | enum | Ver §2.4 |
| `synergy_is_observed` | bool | `true` si la dupla se preguntó; `false` si es predicha |
| `lane_strength` | log-odds | Fuerza en el enfrentamiento 2v2 de bot, centrada en 0 |
| `lane_strength_ci_low`, `lane_strength_ci_high` | log-odds | IC 95 % |
| `lane_strength_n` | conteo | Comparaciones de tipo 3 variante 2v2 que incluyeron esta dupla |
| `lane_strength_support` | enum | Ver §2.4 |
| `lane_strength_is_observed` | bool | `true` si la dupla se preguntó; `false` si es predicha |
| `patch_window` | text | Parches incluidos |

**19 columnas, 2 magnitudes medidas por dupla.**

Los pares de roles posibles son los tres contextos del tipo 4: `adc` + `support`, `top` +
`jungle` y `mid` + `jungle`. `lane_strength` sólo tiene valor en la dupla de bot (`adc` +
`support`): el enfrentamiento 2v2 se pregunta únicamente sobre el carril inferior, que es donde
dos campeones comparten oponentes durante la fase de líneas. En las duplas con jungla la columna
queda vacía y sólo se mide `synergy`.

> **Cambiado el 08/10/2026.** `duo_context` (`bot` \| `top_jungle` \| `mid_jungle`) se reemplazó
> por `role_a` y `role_b` ([ADR-023](13-adr/ADR-023-salida-en-formato-largo.md)). La columna nueva
> dice además qué campeón juega qué rol, que el contexto solo no decía. El orden canónico sigue
> siendo `a_id < b_id`, así que `role_a` puede ser el `support` y `role_b` el `adc`.

Ambas magnitudes son **simétricas**: acompañar a A con B es lo mismo que acompañar a B con A. Se
almacenan en forma canónica (`a_id < b_id`) por la misma razón que la matriz de matchups.

### 5.1 Por qué no hay una matriz de dupla contra dupla

El tipo 3 en su variante 2v2 recolecta enfrentamientos entre duplas concretas, así que en principio
podría emitirse una matriz `dupla × dupla` análoga a `matchup_matrix.csv`. **No se emite**, por una
razón de densidad: el espacio de duplas es el cuadrado del de campeones, y el de pares de duplas su
cuadrado otra vez. Con el volumen del piloto, esa matriz sería casi enteramente
`is_observed = false`, es decir, un archivo grande de predicciones del modelo con casi nada de
evidencia adentro.

La ventaja de una dupla sobre otra se deriva de la diferencia de sus `lane_strength`, exactamente
como el modelo la calcularía. Quien la necesite la puede computar en una línea; entregarla
precalculada sólo agregaría peso y una falsa sensación de cobertura.

El espacio de duplas es mucho mayor que el de campeones individuales, así que este archivo es el de
soporte más flojo de los tres y el que más filas tendrá marcadas como predichas. Los tipos 4 y la
variante 2v2 suman una fracción baja de la mezcla de preguntas: su prioridad relativa es
deliberadamente menor que la de los tipos 1, 2 y 3.

---

## 6. Cómo lo consume el laboratorio

```python
import pandas as pd

dims = pd.read_csv("champion_dimensions_v16.20.csv")

# Una dimensión, sólo lo que está bien sostenido
engage = dims[(dims.dimension == "engage") & (dims.score_support == "solid")]
engage.nlargest(10, "score")[["display_name", "score", "score_ci_low", "score_ci_high"]]

# Las ocho dimensiones de un campeón, a lo ancho si hace falta
dims[dims.riot_key == "Leona"].pivot(index="riot_key", columns="dimension", values="score")

# La curva temporal de un campeón
peak = pd.read_csv("peak_timing_v16.20.csv")
peak.loc[peak.riot_key == "Kayle",
         ["peak_minute", "power_at_5", "power_at_10", "power_at_15",
          "power_at_20", "power_at_25"]]

# Fuerza de línea en mid, sin las filas vacías de quien no juega mid
lanes = pd.read_csv("champion_lane_strength_v16.20.csv")
lanes[(lanes.role == "mid") & lanes.lane_strength.notna()]

# Matchups observados de un campeón en mid
mus = pd.read_csv("matchup_matrix_v16.20.csv")
mus[(mus.role == "mid") & mus.is_observed &
    ((mus.champion_a_key == "Syndra") | (mus.champion_b_key == "Syndra"))]
```

Cómo estas mediciones se combinan para describir una partida es decisión del laboratorio. La
frontera de la práctica es el CSV.

---

## 7. Trazabilidad

Toda entrega es auditable. Para cada archivo, `exports` registra:

`sha256` · `row_count` · `column_count` · `responses_included` · `respondents_included` ·
`min_trust_applied` · `patch_window` · `decay_halflife_days` · `bootstrap_samples` ·
`aggregation_version` · `created_at`

Con esos parámetros y la tabla `responses` —que es append-only— cualquier corrida se puede
reproducir bit a bit. Si un resultado del laboratorio resulta sorprendente, se puede reconstruir
exactamente el archivo que lo produjo.
