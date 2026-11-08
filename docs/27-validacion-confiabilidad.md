# 27 — Validación de confiabilidad y el Informe de Calidad de Datos

> Estado: **v1** · Ola 4 · Semana 10 · 07/11/2026
>
> Las definiciones que ningún documento previo fijaba —qué tipos llevan alfa, con qué umbral, sobre
> qué población se miden el test-retest y las honeypots, cómo se cruza una honeypot con las demás
> señales, cómo se resume el trust por horas, qué es «cobertura por par», el idioma del informe y
> qué se hace con el bootstrap por respondedor mientras no hay piloto— las decidió el alumno el
> 07/11/2026. Cada una está marcada en su sección.

Este documento dice **qué se mide para saber si los seis CSV son confiables** y **cómo se entrega
esa medición**: el Informe de Calidad de Datos, `data_quality_report_v<patch>.md`, que acompaña
cada exportación (RF-511, meta M8, [`26-esquema-de-salida.md`](26-esquema-de-salida.md) §1).

[`25-agregacion.md`](25-agregacion.md) §3.4 a §3.8 y §4.7 ya fijan buena parte del contenido:
cómo se describe la muestra, la estabilidad por segmento, la cobertura por rol, el control del
trust por horas, la auditoría de honeypots y las dos versiones del intervalo. Acá no se repiten:
se citan, y se agrega lo que faltaba.

---

## 1. Qué valida y qué no

**El informe reporta; no corrige.** Ninguna métrica de este documento cambia una celda de los CSV,
un `_support` ni un peso. Una dimensión con alfa bajo, un segmento que ordena distinto o una
honeypot sospechosa son **hallazgos declarados** para que el laboratorio decida con su propio
criterio, igual que `_support` no excluye nada (26 §2.4, [ADR-011](13-adr/ADR-011-support-level-en-vez-de-excluir.md)).

Tampoco retira honeypots ni marca respondedores: eso lo siguen haciendo los jobs de
[`22-calidad-de-datos.md`](22-calidad-de-datos.md). El informe es una fotografía de la corrida.

### 1.1 Sobre qué datos se calcula cada parte

| Parte | Población | Por qué |
|---|---|---|
| Muestra, concentración, alfa, cobertura, anchos, segmentos, cobertura por rol (§2, §5–§7) | **Las filas de la corrida**: las que pasan los cinco filtros de 25 §1.2 | Describen exactamente lo que está en los CSV |
| Test-retest, honeypots, trust por horas (§3, §4, §7.3) | **Respondedores no marcados con al menos una respuesta en la ventana, sin filtro de trust** (decisión del 07/11) | El trust se calcula con honeypots y retests: filtrar por trust antes de medirlos los inflaría por construcción. Es la misma regla que ya usa el *pass rate* del job (22 §3.4: los marcados no cuentan) |
| Huella (§8) | Respondedores marcados con al menos una respuesta en la ventana | Es lo que la corrida dejó afuera por esa causa (22 §6.3) |

«Una respuesta en la ventana» es una fila de `responses` cuyo `patch_id` está en la ventana de la
corrida, resuelta igual que en 25 §1.2.

### 1.2 Qué cuenta como «respuesta»

Una fila de `responses`. En el tipo 1 eso es **una comparación**: un ranking contestado son hasta
diez filas ([ADR-022](13-adr/ADR-022-tipo-1-ranking-de-cinco.md)). Es la misma unidad que cuenta
`_n` (25 §4.3), y por eso es la que usa el informe. Donde se cuentan respondedores, se dice.

---

## 2. Acuerdo inter-anotador: alfa de Krippendorff

> **Decisión del 07/11/2026:** se calcula para **los cinco tipos**, no sólo para las dimensiones.

### 2.1 Por qué alfa

Es la medida de acuerdo que admite **cualquier cantidad de anotadores por unidad, datos
faltantes, y escalas nominales, ordinales y de intervalo** con una sola definición
(Krippendorff, *Content Analysis*, 2004; *Computing Krippendorff's Alpha-Reliability*, 2011). En
DraftSense cada pregunta la contesta un subconjunto distinto de personas y casi nadie contesta
todas: un kappa de Cohen o de Fleiss no se puede aplicar sin descartar casi todo el dato.

Alfa supone que los anotadores responden de forma independiente. La gamificación está diseñada
para no romper ese supuesto ([`23-gamificacion.md`](23-gamificacion.md), al principio): ninguna
recompensa depende de coincidir con el consenso.

### 2.2 La fórmula

Para una magnitud se arma la **matriz de coincidencias** sobre todas las unidades con al menos dos
valores. Con `n_uc` = cantidad de valores `c` en la unidad `u` y `m_u` = cantidad de valores de
la unidad:

```
o_ck = Σ_u  (n_uc · n_uk − [c = k] · n_uc) / (m_u − 1)       # sólo unidades con m_u ≥ 2
n_c  = Σ_k o_ck                n = Σ_c n_c                    # valores aparejables

α = 1 − (n − 1) · Σ_{c,k} o_ck · δ²(c,k)  /  Σ_{c,k} n_c · n_k · δ²(c,k)
```

Con la métrica de distancia `δ²` que corresponda a la escala:

| Escala | `δ²(c, k)` |
|---|---|
| Nominal | `0` si `c = k`, `1` si no |
| Ordinal | `( Σ_{g entre c y k} n_g − (n_c + n_k)/2 )²` |
| Intervalo | `(c − k)²` |

**Alfa no está definido** si hay menos de dos valores aparejables o si el denominador es cero
(todos los valores de la magnitud son iguales). Entonces el informe dice *no calculable* con su
`n`, nunca un número.

### 2.3 Unidad y valor de cada magnitud

| Magnitud | Una alfa por | Unidad | Valor | Escala |
|---|---|---|---|---|
| Tipo 1 | Dimensión (8) | El par no ordenado de campeones | Cuál de los dos eligió: el de menor id o el de mayor id | Nominal |
| Tipo 3, 1v1 | Rol (`top`, `mid`, `adc`) | El par no ordenado de campeones | El nivel 0–4 (`b_strong` … `a_strong`), orientado al campeón de menor id | Ordinal |
| Tipo 3, 2v2 | Contexto `bot` | El par no ordenado de duplas | El nivel 0–4, orientado a la dupla menor | Ordinal |
| Tipo 4 | Contexto (`bot`, `top_jungle`, `mid_jungle`) | El par no ordenado de duplas | `pair_1` / `similar` / `pair_2`, orientado a la dupla menor | Nominal |
| Tipo 2 | — (una) | El campeón | El minuto | Intervalo |
| Tipo 5 | Atributo (7) | El campeón | Marcado / no marcado | Nominal |

- **Orientar** quiere decir que si la pregunta presentaba al campeón (o la dupla) de mayor id
  primero, el nivel se espeja (`a_strong` ↔ `b_strong`, `pair_1` ↔ `pair_2`). Sin eso, dos
  personas que opinan lo mismo sobre preguntas armadas en distinto orden contarían como
  desacuerdo. La dupla se ordena por (campeón, rol), como en `duo_features`.
- **En el tipo 1 el valor es el lado, no el campeón.** Con el id del campeón como categoría, el
  desacuerdo esperado se calcularía sobre las decenas de campeones del pool, cuando cada persona
  sólo pudo elegir entre dos: saldría inflado y el alfa, también.
- **`unknown` y «Not sure» quedan afuera**: no son un valor de la escala. Es la misma regla que
  `_n` (25 §1.4).
- **Sin ponderar.** Alfa no admite pesos por anotador en su definición clásica, y una versión
  ponderada no sería comparable con ningún valor publicado. El trust ya actuó como filtro (la
  corrida excluye a quien está bajo `min_trust`); dentro de la corrida, todos cuentan igual.
- Un respondedor puede aportar dos valores a una misma unidad si la contestó en dos parches de la
  ventana. Alfa lo admite: la unidad es la pregunta, no el anotador.

### 2.4 Criterio de aceptación

> **Decisión del 07/11/2026:** los umbrales que propone Krippendorff (2004), que **sólo se reportan**.

| `α` | Lectura en el informe |
|---|---|
| `≥ 0.800` | **confiable** |
| `0.667 ≤ α < 0.800` | **tentativo**: sirve para conclusiones provisorias |
| `< 0.667` | **no confiable** |

Una magnitud bajo 0.667 **no** cambia su `_support` ni se saca del CSV: se lista como hallazgo al
principio del informe (§9.2).

Dos advertencias que el informe repite junto a la tabla:

1. **Alfa mide acuerdo, no validez.** Una comunidad entera puede coincidir en algo equivocado.
2. **Alfa bajo en una magnitud de opinión no es necesariamente ruido.** En el tipo 3 hay matchups
   genuinamente discutidos; el `advantage` cerca de cero con IC angosto es justamente ese caso.

---

## 3. Consistencia test-retest

Por tipo —1, 2, 3 (1v1), 3 (2v2), 4 y 5—: cantidad de retests en la ventana que forman par, cuántos
son consistentes y la tasa. **Las reglas son las de 22 §4 y §4.1, sin cambios**, y el código es el
mismo que usa el trust (`backend/app/services/retests.py`, `is_consistent`). Un retest cuyo par no
cuenta —`unknown` en el tipo 1— no suma.

Población: §1.1. El retest es de la ventana si la **repetición** lo es; la original puede ser de un
parche anterior.

---

## 4. Honeypots

### 4.1 *Pass rate*

Global y por honeypot, con la regla de 22 §3.5: coincide con `expected_answer` → aprobada; no
coincide → fallada; `unknown` → no es intento. Es honeypot la pregunta con `is_honeypot` vigente al
correr, que es la misma regla con la que la corrida las deja afuera (25 §1.2): una honeypot ya
retirada no aparece.

Por cada parche de la ventana, la cantidad de honeypots activas. **Un parche sin honeypots activas
es un trust congelado** que no se ve en ninguna otra parte
([ADR-024](13-adr/ADR-024-activacion-explicita-de-parche.md)), y el informe lo advierte.

### 4.2 Por segmento de rango

El *pass rate* de cada honeypot en los cinco segmentos de 25 §3.5 (`low`, `mid`, `high`,
`unranked`, `undeclared`), con los intentos de cada uno. Es el control de 25 §3.8: una honeypot que
los segmentos altos fallan tanto como los bajos es sospechosa de estar mal redactada.

### 4.3 El cruce con las demás señales

> **Decisión del 07/11/2026**, que concreta la frase de 22 §3.4 («si quienes fallan una honeypot
> son consistentes en todo lo demás, la sospechosa es la honeypot»).

Para cada honeypot con **al menos `quality.honeypot_min_attempts` intentos** en la ventana (40, el
mismo piso que el retiro automático):

- La tasa de consistencia test-retest (§3) de los respondedores que **la fallaron**, sumando todos
  sus retests de la ventana.
- La misma tasa para los que **la aprobaron**.
- **Sospechosa** si los que la fallaron tienen una tasa **mayor o igual** que los que la
  aprobaron, y los dos grupos tienen al menos un retest.

No retira nada: alimenta la revisión manual del catálogo, igual que §4.2.

---

## 5. Cobertura

> **Decisión del 07/11/2026** sobre qué es «cobertura por par».

### 5.1 Por par

Para cada magnitud pareada, sobre las filas de la corrida:

| Magnitud | El «par» | Pares posibles |
|---|---|---|
| Tipo 1, por dimensión | Dos campeones | `C(k, 2)`, `k` = campeones del pool |
| Tipo 3 1v1, por rol | Dos campeones | `C(k, 2)`, `k` = campeones del pool con ese rol |
| Tipo 3 2v2 y tipo 4, por contexto | **La dupla**: dos campeones que juegan juntos | Las duplas válidas del contexto con los dos integrantes en el pool (25 §8.2, nota del 29/10) |

En las duplas el «par» es la dupla y no el enfrentamiento entre dos duplas: las combinaciones de
dupla contra dupla son tantas que su porcentaje sería siempre cercano a cero y no diría nada. La
dupla es además la fila de `duo_features`.

Se reporta: pares posibles, pares con al menos una comparación y su porcentaje, y el mínimo, la
mediana y el máximo de comparaciones por par observado. En el tipo 1 cuentan sólo las decisivas,
como `_n`.

### 5.2 Por nivel de soporte

Para cada magnitud de los seis CSV, cuántas filas quedaron `solid`, `limited` e `insufficient`.
Es el resumen de un vistazo de 26 §2.4.

### 5.3 Conectividad y remuestreos descartados

Por cada uno de los 15 ajustes de 25 §8.2: comparaciones, componentes del grafo
([ADR-008](13-adr/ADR-008-conectividad-por-componentes.md)), remuestreos intentados y descartados,
y si el ajuste quedó `insufficient` por superar el 5 % (25 §4.2). Con más de una componente, el
informe lo advierte.

### 5.4 Dos chequeos de consistencia interna

- **Picos con muestra suficiente e intervalo ancho**: campeones con `peak_minute_n` en el umbral de
  `solid` pero ancho por encima. Es como se detecta una distribución bimodal
  ([`20-tipos-de-pregunta.md`](20-tipos-de-pregunta.md) §3, «Casos borde»): se listan.
- **`proportion_n` distinto entre los atributos de un campeón**: no debería pasar salvo un cambio
  de catálogo en la ventana (25 §5.6). Se listan, o se dice que no hay.

---

## 6. Incertidumbre

### 6.1 Ancho medio del intervalo

Por magnitud, la media de `_ci_high − _ci_low` sobre las filas con intervalo, en la unidad de la
columna (log-odds, minutos, escala −1…+1, proporción).

### 6.2 Las dos versiones del bootstrap — 25 §4.7

Para **las 8 dimensiones**, que es lo que fija 25 §4.7 («el ancho medio de ambas, por dimensión»):

- **Sobre comparaciones**, el de 26 §3.2: el que se publica en el CSV.
- **Por respondedor**: se remuestrean con reemplazo los respondedores que aportan comparaciones
  decisivas a esa dimensión, y cada comparación entra tantas veces como salió su respondedor. Las
  mismas tres reglas de 25 §4.2: mismo `B`, **re-centrar dentro de cada remuestreo**, y descartar
  el que parta las componentes originales, con el tope de 3·B intentos y el 5 %. Las diez
  comparaciones de un ranking quedan agrupadas solas (25 §4.7, nota del 08/10).

El informe publica los dos anchos medios y su cociente. **Sólo se publican en el informe**: los CSV
siguen con el bootstrap sobre comparaciones.

### 6.3 Índice de concentración y el criterio del 40 %

El decil más activo son los `⌈N / 10⌉` respondedores con más filas (§1.2). El informe da dos
índices:

- Sobre **todas las filas** de la corrida: el de 25 §3.4.
- Sobre las **comparaciones decisivas del tipo 1**: el que decide 25 §4.7. Si supera **0.40**, el
  informe lo dice como hallazgo: «corresponde un ADR que reemplace 26 §3.2».

> **Decisión del 07/11/2026:** el piloto quedó para el final, así que **la decisión de 25 §4.7 se
> toma con los datos del piloto**, no con la seed sintética, cuya distribución de actividad es
> inventada. Hasta entonces la corrida calcula las dos versiones y el informe aplica el criterio,
> pero ningún CSV cambia.

---

## 7. Los datos declarados — 25 §3.4 a §3.8

### 7.1 Descripción de la muestra — 25 §3.4

Las tres tablas de 25 §3.4 —rango, rol principal y horas—, con los valores en el orden del
esquema (`VALID_RANKS`, `lane_role`, `VALID_HOURS_BUCKETS`) y `(no dijo)` al final. **Antes que las
tablas, el tamaño de `undeclared`** (25 §3.9).

### 7.2 Estabilidad por segmento — 25 §3.5

Exactamente el procedimiento de 25 §3.5, con los pisos `aggregation.segment_min_respondents` (15) y
`aggregation.segment_min_comparisons` (300), y con las dos variables ordenadas:

- **Rango**: los cinco segmentos de 25 §3.5.
- **Horas**: los cuatro buckets de `VALID_HOURS_BUCKETS` más `undeclared`. 25 §3.5 dice «el mismo
  análisis»; no agrupa buckets, así que se usan tal cual.

Las tres métricas de 25 §3.5 se calculan **entre cada par de segmentos calculables** y sobre los
campeones del pool con valor en los dos: ρ de Spearman, diferencia absoluta media de los scores
centrados, y cuántos campeones cambian de `_support`. El disparador de 25 §3.10 —ρ entre `low` y
`high` por debajo de 0.70 en tres o más dimensiones calculables— se evalúa y, si se cumple, va a
los hallazgos.

### 7.3 Cobertura por rol — 25 §3.6

Para `top`, `mid` y `adc` del 1v1: respuestas, porcentaje de quienes declararon ese rol como
principal y porcentaje sin rol declarado. Para el 2v2 de `bot`, el porcentaje de quienes declararon
`adc` **o** `support`, que son los dos roles del carril inferior.

### 7.4 Trust por horas — 25 §3.7

> **Decisión del 07/11/2026:** cuartiles y ρ de Spearman.

Población: §1.1. Por bucket de horas y `(no dijo)`: `n`, mínimo, P25, mediana, P75 y máximo del
`trust_score`; y el ρ de Spearman entre el orden del bucket (`<5` = 0 … `30+` = 3) y el trust,
sobre quienes declararon. 25 §3.7 dice cómo se lee: una relación positiva y suave es la esperada.

### 7.5 Honeypots por segmento — 25 §3.8

Es §4.2.

---

## 8. Huella — 22 §6.3

Respondedores marcados con actividad en la ventana, cuántas respuestas suyas quedaron fuera de la
corrida por esa causa, el valor de `quality.fingerprint_max_identities`, y la advertencia de 22
§6.3: **una parte puede ser una red compartida** con equipos clonados.

---

## 9. El informe

### 9.1 El archivo

- Nombre: `data_quality_report_v<patch>.md`, con el `<patch>` de los CSV, en la misma carpeta.
- **Idioma: español** (decisión del 07/11/2026). Los identificadores —nombres de columna, códigos
  de dimensión y de atributo, niveles de soporte— quedan en inglés y en código, como en los CSV.
- Markdown, UTF-8 sin BOM, fin de línea `\n`.
- **Determinista**: sin fecha de generación ni nada que dependa del reloj; la única fecha es
  `exported_at`. Las tablas en el orden fijo de los CSV (25 §4.6). Los números con formato fijo:
  `α`, `ρ`, tasas, proporciones y anchos con `%.3f`; porcentajes con `%.1f`; conteos enteros.
  **Entra en CA-408**: dos corridas iguales dan el mismo SHA-256 también para el informe.
- Se registra en `exports` con `file_kind = 'quality_report'`, el mismo `params`, y
  `row_count` = líneas del archivo y `column_count` = 0 (no es una tabla; 11 §3.11 exige las dos
  columnas no nulas). `responses_included` y `respondents_included` son los de la corrida entera.

### 9.2 Orden de las secciones

1. **Encabezado**: ventana de parches y el aviso de que un archivo `v<patch>` mezcla los parches
   de la ventana con decaimiento ([ADR-004](13-adr/ADR-004-ventana-de-parches-con-decaimiento.md));
   los parámetros de la corrida y su semilla; los SHA-256 de los seis CSV.
2. **Hallazgos**: lista de lo que requiere atención —alfa no confiable, grafo partido, magnitud
   `insufficient` por remuestreos, concentración sobre 0.40, disparador de 25 §3.10, honeypots
   sospechosas, parche sin honeypots—, o «Sin hallazgos».
3. Lo que entró y lo que no: respuestas de la ventana, y cuántas quedaron fuera por honeypot,
   retest, huella y trust.
4. Muestra (§7.1).
5. Acuerdo inter-anotador (§2).
6. Test-retest (§3).
7. Honeypots (§4).
8. Cobertura (§5).
9. Incertidumbre (§6).
10. Estabilidad por segmento, cobertura por rol y trust por horas (§7.2–§7.4).
11. Huella (§8).
12. **Advertencias de lectura**, siempre presentes:
    - `_norm` no es comparable entre exportaciones (26 §2.5).
    - En `champion_traits`, la proporción es **entre quienes marcaron al menos un atributo**
      ([ADR-027](13-adr/ADR-027-tipo-5-al-menos-un-atributo.md)).
    - El idioma en que se contestó no se registra, así que no hay análisis por idioma
      ([ADR-028](13-adr/ADR-028-idioma-por-parametro.md)).
    - Los intervalos publicados suponen comparaciones independientes (§6.2).

### 9.3 Lo que queda para el piloto

Tres calibraciones que los documentos previos ponen en el informe y que **sólo tienen sentido con
datos reales**: la vida media ([ADR-004](13-adr/ADR-004-ventana-de-parches-con-decaimiento.md)), la
sensibilidad de `σ` ([ADR-009](13-adr/ADR-009-curva-de-poder-gaussiana.md)) y los umbrales de
`_support` (25 §9). El informe de esta versión **publica el valor usado** de cada uno, no un
análisis de sensibilidad: no hay un procedimiento definido para él, y se especifica junto con el
plan piloto ([`34-plan-piloto.md`](34-plan-piloto.md)).

---

## 10. Implementación

`aggregation/quality/`, un módulo por sección; lo llama `pipeline.run` en el paso 7 de 25 §8.2,
después de los CSV.

**La partición de trabajo se extiende sin tocar la existente.** Los ajustes nuevos —el bootstrap
por respondedor de las 8 dimensiones, y los ajustes por segmento: los cinco de rango y los cinco de
horas, cada uno con sus 8 dimensiones— van **después** de los 17 de la semana 9 y reciben los
generadores hijos siguientes de la misma semilla. `SeedSequence.spawn` da el mismo hijo en la
posición `i` sin importar cuántos se pidan, así que **los seis CSV no cambian de SHA-256** por
agregar el informe, y `AGGREGATION_VERSION` no cambia.

Las consultas de §3, §4, §7.4 y §8 son propias del módulo: esas filas —retests, honeypots,
respondedores fuera de la corrida— no están en el conjunto filtrado de 25 §1.1, a propósito.

---

## 11. Verificación

| Qué se prueba | Cómo | CA |
|---|---|---|
| El alfa es el de Krippendorff | El ejemplo resuelto de Krippendorff (2011): nominal 0.743, ordinal 0.815, intervalo 0.849 | CA-410 |
| Alfa no se inventa con datos insuficientes | Una magnitud con un solo valor por unidad ⇒ *no calculable* | CA-410 |
| La orientación del par | Dos respuestas iguales sobre preguntas armadas al revés ⇒ acuerdo perfecto | CA-410 |
| Test-retest con las reglas de 22 §4 | Pares consistentes e inconsistentes de cada tipo ⇒ la tasa esperada | CA-411 |
| Honeypot sospechosa | Quienes la fallan son más consistentes que quienes la aprueban ⇒ marcada | CA-412 |
| La población sin filtro de trust | Un respondedor bajo `min_trust` cuenta en el *pass rate* y no en el alfa | CA-412 |
| Concentración y el 40 % | Un decil que aporta el 50 % ⇒ hallazgo | CA-413 |
| El bootstrap por respondedor agrupa | Con un respondedor que aporta todo, el IC por respondedor es más ancho | CA-413 |
| Segmento bajo el piso | 14 respondedores ⇒ *no calculable* con su `n` | CA-414 |
| El informe es reproducible y no toca los CSV | Dos corridas ⇒ el mismo SHA-256 en los siete archivos, y los seis CSV iguales a los de antes del informe | CA-415 |

---

Ver el índice en [`README.md`](README.md) y las decisiones ya cerradas en [`13-adr/`](13-adr/).
