# 20 — Los cinco tipos de pregunta

> Estado: **v1** · Última revisión: 31/08/2026

Especifica cada tipo de pregunta de punta a punta: qué mide, cómo se enuncia, cómo se ve, qué
payload produce, cómo se generan las candidatas, cómo se agrega y qué pasa en los casos borde.

Los cinco tipos están **comprometidos en el alcance de la práctica**. El tipo 3 tiene dos variantes
que comparten enunciado, escala y modelo de agregación.

---

## 1. Principios comunes

### 1.1 La regla de los cinco segundos

Cada tarjeta se responde en **cinco a diez segundos**. Todo lo que compita con eso —texto largo,
opciones chicas, scroll— cuesta respuestas. Una sesión típica son 20 preguntas en 2–3 minutos.

Consecuencias de diseño que se aplican a todos los tipos:

- Una pregunta por pantalla, sin scroll.
- Área táctil de al menos 44 px de lado en cualquier opción.
- Los íconos de campeón son la información principal; el nombre va debajo, chico.
- La respuesta se registra al primer toque, sin botón de confirmar. Excepción: el tipo 5, que es
  multi-selección y necesita un cierre explícito.

### 1.2 Enunciado corto, definición a un toque

El enunciado es una línea en tipografía grande. Al lado, un ícono `?` que despliega la definición
del concepto medido.

Esa definición no es decorativa: **es lo que hace que dos personas midan lo mismo**. El acuerdo
inter-anotador que se reporta en el Informe de Calidad de Datos depende de que "engage" signifique
lo mismo para todos. Dejarla a un toque de distancia resuelve la tensión entre el ritmo y la
consistencia: quien ya sabe no la abre, quien duda la consulta.

El texto de las definiciones vive en las tablas `dimensions` y `traits`, no en el código.

### 1.3 Los honeypots son indistinguibles

Una pregunta honeypot se ve exactamente igual que una real. `is_honeypot` **nunca** se expone al
cliente y `expected_answer` no sale de la base. Cualquier señal visual las invalidaría.

### 1.4 El idioma es inglés

Todos los enunciados de esta especificación son el texto literal que ve el usuario
([ADR-010](13-adr/ADR-010-interfaz-en-ingles.md)). La terminología es la nativa del juego: se dice
*poke*, no "sustained ranged damage".

---

## 2. Tipo 1 — Comparación pareada por dimensión

**`pairwise_dimension`** · 50 % de la sesión · el tipo de mayor valor y el primero en implementarse.

### Qué mide

La posición relativa de cada campeón en ocho dimensiones funcionales. Es la fuente de 56 de las 126
columnas de `champion_features.csv`.

### Enunciado

```
Who has more engage?
```

El ícono `?` despliega la definición de la dimensión desde `dimensions.description_en`:

| `code` | Enunciado | Definición desplegable |
|---|---|---|
| `engage` | Who has more **engage**? | Starting fights on your terms. |
| `poke` | Who has more **poke**? | Chipping enemies down from range without committing. |
| `pick` | Who has more **pick potential**? | Isolating and killing a single target. |
| `peel` | Who has more **peel**? | Protecting an ally from divers and assassins. |
| `mobility` | Who has more **mobility**? | Dashes, blinks and repositioning tools. |
| `scaling` | Who **scales** better? | How much stronger they get with gold and levels. |
| `cc` | Who has more **crowd control**? | Amount and reliability of stuns, roots and slows. |
| `waveclear` | Who has better **waveclear**? | How fast they clear minion waves. |

### Tarjeta

```
┌─────────────────────────────┐
│  Who has more engage?    (?)│
│                             │
│   ┌───────┐     ┌───────┐   │
│   │       │     │       │   │
│   │ [img] │     │ [img] │   │
│   │       │     │       │   │
│   └───────┘     └───────┘   │
│    Alistar       Yasuo      │
│                             │
│      ┌───────────────┐      │
│      │  Not sure     │      │
│      └───────────────┘      │
└─────────────────────────────┘
```

### Payload

```jsonc
{ "question_id": 88412, "answer": { "choice": "a" }, "response_time_ms": 2140 }
```

`choice` ∈ `a` | `b` | `unknown`.

### Generación de candidatas

Pares de campeones **activos y en un `pool_tier` habilitado**, contra cualquier dimensión activa.
Se generan perezosamente: la pregunta se crea la primera vez que el sampler la elige, no por
precómputo del producto cartesiano.

**Los pares no se restringen por rol, y eso es deliberado.** Comparar el *waveclear* de un support
con el de un mid es una pregunta legítima —waveclear es waveclear— y sobre todo es lo que mantiene
**conectado el grafo de comparaciones**. Si sólo se compararan campeones del mismo rol, Bradley-Terry
vería cinco componentes desconectadas por dimensión y no podría ubicar un rol respecto de otro
([ADR-008](13-adr/ADR-008-conectividad-por-componentes.md)).

### Agregación

Bradley-Terry ponderado por trust, una corrida **independiente por dimensión**
(`choix.ilsr_pairwise`). Las respuestas `unknown` se **descartan del ajuste pero se registran**: su
tasa por campeón se exporta como `D_unknown_rate` y es una señal de que la dimensión no aplica bien
a ese campeón. IC por bootstrap sobre las comparaciones.

### Casos borde

| Situación | Comportamiento |
|---|---|
| Un campeón del par se desactiva a mitad del piloto | Las respuestas ya dadas se conservan y se agregan; no se generan preguntas nuevas con él |
| Una dimensión se desactiva | Igual: el crudo queda, deja de preguntarse |
| Tasa de `unknown` mayor al 40 % en un par | El sampler lo desprioriza: la pregunta no está produciendo información |
| El campeón queda con menos de 3 comparaciones | Se exporta con `support = insufficient`, nunca vacío por omisión |

---

## 3. Tipo 2 — Slider de pico de poder

**`peak_timing`** · 20 % de la sesión · aporta la dimensión temporal ausente en el esquema actual.

### Qué mide

El minuto en que un campeón alcanza su máximo poder relativo. De ese único número se deriva la
curva de poder completa ([ADR-009](13-adr/ADR-009-curva-de-poder-gaussiana.md)).

### Enunciado

```
When does Kayle peak?
```

Definición desplegable: *"The point in the game where this champion is at their strongest compared
to everyone else."*

### Tarjeta

```
┌─────────────────────────────┐
│  When does Kayle peak?   (?)│
│                             │
│        ┌───────┐            │
│        │ [img] │            │
│        └───────┘            │
│         Kayle               │
│                             │
│           ▼ 27 min          │
│  ├────────────────────────┤ │
│  0        15        30    40│
│  laning   mid game  late    │
│                             │
│      ┌───────────────┐      │
│      │   Confirm     │      │
│      └───────────────┘      │
└─────────────────────────────┘
```

Es el único tipo, junto al 5, que necesita confirmación explícita: un slider no tiene "primer
toque" que valga como respuesta.

El slider **no arranca en una posición neutra útil**. Arranca en 20 (el centro) y el valor sólo se
registra si el usuario lo movió o tocó *Confirm* deliberadamente; si confirma sin tocar, se guarda
igual, pero el `response_time_ms` bajo lo delata como respuesta apurada.

### Payload

```jsonc
{ "question_id": 91002, "answer": { "minute": 27 }, "response_time_ms": 5310 }
```

`minute` entero entre 0 y 40.

### Generación de candidatas

Un campeón activo de un tier habilitado. Una pregunta por (campeón, parche).

### Agregación

**Mediana ponderada** por trust, con IC bootstrap. Se usa mediana y no media porque la distribución
es asimétrica y porque la mediana tolera mucho mejor a quien arrastra el slider al azar: un puñado
de valores en 0 o en 40 desplaza una media, casi no mueve una mediana.

### Casos borde

| Situación | Comportamiento |
|---|---|
| Distribución bimodal (campeón jugado en dos roles con curvas distintas) | La mediana cae en el valle, entre los dos modos. Se detecta por IC ancho y se marca `limited` o `insufficient`; el Informe de Calidad de Datos lo reporta |
| Todas las respuestas en 20 | Sospecha de confirmaciones sin mover el slider. El job de patrones degenerados lo marca |
| Menos de 10 respuestas | `support = insufficient`; la curva `power_at_*` se calcula igual pero hereda la incertidumbre |

---

## 4. Tipo 3 — Enfrentamiento de línea

**`lane_matchup`** · 20 % de la sesión (15 % variante 1v1, 5 % variante 2v2).

Dos variantes que comparten enunciado, escala de cinco niveles y modelo de agregación. Lo único que
cambia es **qué entidad compite**: un campeón o una dupla. Por eso son una variante y no un sexto
tipo de pregunta.

Ambas se fijan **al minuto 10**, el cierre típico de la fase de líneas. Un punto de referencia común
hace que todas las respuestas sean comparables entre sí; sin él, cada persona contestaría pensando
en un momento distinto y esa varianza quedaría mezclada dentro del estimador.

### 4.1 Variante 1v1 — top, mid, adc

#### Enunciado

```
Who wins this lane at 10 minutes?
```

Definición desplegable: *"Assume equal skill and no jungle interference."* — necesaria, porque sin
ella cada uno responde sobre un escenario distinto.

#### Tarjeta

```
┌─────────────────────────────┐
│  Who wins this lane         │
│  at 10 minutes?          (?)│
│              MID            │
│   ┌───────┐     ┌───────┐   │
│   │ [img] │  vs │ [img] │   │
│   └───────┘     └───────┘   │
│    Syndra        Zed        │
│                             │
│  ┌───────────────────────┐  │
│  │  Syndra wins hard     │  │
│  ├───────────────────────┤  │
│  │  Syndra wins slightly │  │
│  ├───────────────────────┤  │
│  │  Even                 │  │
│  ├───────────────────────┤  │
│  │  Zed wins slightly    │  │
│  ├───────────────────────┤  │
│  │  Zed wins hard        │  │
│  └───────────────────────┘  │
└─────────────────────────────┘
```

Los botones llevan el **nombre del campeón**, no "A" y "B": elimina el paso mental de mapear letra
a ícono.

#### Payload

```jsonc
{ "question_id": 77310, "answer": { "choice": "a_slight" }, "response_time_ms": 4120 }
```

`choice` ∈ `a_strong` | `a_slight` | `even` | `b_slight` | `b_strong`.

#### Generación de candidatas

Pares de campeones que **comparten un rol** en {`top`, `mid`, `adc`}, según el arreglo
`champions.roles`. Una pregunta por (par, rol, parche): el mismo par puede preguntarse en top y en
mid si ambos juegan los dos.

**La jungla no entra.** Un jungla no tiene oponente fijo con quien intercambiar durante diez
minutos, así que la pregunta no tiene una respuesta que la gente pueda dar con confianza. Los
junglas quedan caracterizados por las ocho dimensiones del tipo 1, que sí aplican a todos.

#### Agregación

Bradley-Terry con empates y margen (**modelo Rao-Kupper**), ajustado por rol. Los cinco niveles se
mapean a `{a_strong: +1, a_slight: +0.5, even: 0, b_slight: −0.5, b_strong: −1}`.

Salida: `lane_strength_{top,mid,adc}` en `champion_features.csv`, y las filas de
`matchup_matrix.csv`.

### 4.2 Variante 2v2 — bot

#### Enunciado

```
Which bot lane wins at 10 minutes?
```

Definición desplegable: *"Which pair beats the other in lane. Not about how well each pair works
together — that's a different question."*

Esa segunda frase existe para separarlo del tipo 4, que se ve parecido y mide otra cosa.

#### Tarjeta

```
┌─────────────────────────────┐
│  Which bot lane wins        │
│  at 10 minutes?          (?)│
│                             │
│  ┌───────────────────────┐  │
│  │ [img] [img]           │  │
│  │ Caitlyn + Lux         │  │
│  └───────────────────────┘  │
│            vs               │
│  ┌───────────────────────┐  │
│  │ [img] [img]           │  │
│  │ Samira + Nautilus     │  │
│  └───────────────────────┘  │
│                             │
│  ┌───────────────────────┐  │
│  │  Top pair wins hard   │  │
│  │  Top pair wins slight │  │
│  │  Even                 │  │
│  │  Bottom wins slightly │  │
│  │  Bottom wins hard     │  │
│  └───────────────────────┘  │
└─────────────────────────────┘
```

Las duplas van **apiladas verticalmente**, no cuatro íconos en fila: en un teléfono, cuatro íconos
en línea quedan por debajo del área táctil mínima y además no comunican qué campeón va con cuál.

#### Payload

Idéntico al 1v1. `a` es la dupla de arriba, `b` la de abajo.

#### Generación de candidatas

Dos duplas de bot distintas, cada una formada por **un campeón con rol `adc` y uno con rol
`support`**, los cuatro activos y en tiers habilitados. Los cuatro campeones deben ser distintos.

#### Agregación

Rao-Kupper tomando cada **dupla como competidor**. Salida: `lane_strength` en `duo_features.csv`.

### 4.3 Casos borde de ambas variantes

| Situación | Comportamiento |
|---|---|
| Un campeón cambia de rol entre parches | Las preguntas viejas se conservan con su rol original; las nuevas usan el rol vigente |
| Tasa de `even` superior al 60 % en un par | Señal legítima de matchup equilibrado, no de ruido. Se agrega normalmente |
| Un rol queda con el grafo desconectado | El job de conectividad marca aristas puente; si al cierre sigue partido, esos scores salen `insufficient` |
| Campeón sin rol declarado en `champions.roles` | Queda fuera de este tipo. El seeder debe garantizar al menos un rol por campeón activo |

---

## 5. Tipo 4 — Sinergia de dupla

**`duo_synergy`** · 5 % de la sesión.

### Qué mide

Cuánto se complementan dos campeones que juegan juntos — **independientemente de contra quién**.
Es la diferencia clave con la variante 2v2 del tipo 3.

### Enunciado

```
Which duo works better together?
```

Definición desplegable: *"Ignore who they're up against. Which two complement each other better?"*

### Tarjeta

Misma estructura apilada que la variante 2v2, con tres opciones en vez de cinco:

```
  ┌───────────────────────┐
  │  Top pair             │
  ├───────────────────────┤
  │  About the same       │
  ├───────────────────────┤
  │  Bottom pair          │
  └───────────────────────┘
```

### Payload

```jsonc
{ "question_id": 64881, "answer": { "choice": "pair_1" }, "response_time_ms": 6200 }
```

`choice` ∈ `pair_1` | `pair_2` | `similar`.

### Generación de candidatas

Dos duplas del **mismo contexto**, definido por el enum `duo_context`:

| Contexto | Composición |
|---|---|
| `bot` | un `adc` + un `support` |
| `top_jungle` | un `top` + un `jungle` |
| `mid_jungle` | un `mid` + un `jungle` |

Los cuatro campeones distintos, activos y en tiers habilitados. **Sólo se comparan duplas del mismo
contexto**: la sinergia de un dúo de bot no es comparable con la de un dúo mid-jungla.

El espacio de duplas es enorme, así que el sampler lo restringe agresivamente a duplas formadas por
campeones del `pool_tier` 1.

### Agregación

Bradley-Terry tomando cada dupla como competidor, una corrida por contexto. Salida: `synergy` en
`duo_features.csv` y `synergy_mean` por campeón en `champion_features.csv`.

### Casos borde

| Situación | Comportamiento |
|---|---|
| Un campeón juega adc y support | Puede aparecer en cualquiera de los dos lugares de una dupla de bot, pero no en ambos de la misma |
| Duplas con soporte muy bajo | Es lo esperable: es el tipo con menos volumen. `is_observed = false` en la mayoría de las filas del CSV |
| Grafo de duplas desconectado por contexto | Se reporta; el modelo no fuerza una solución artificial |

---

## 6. Tipo 5 — Multi-selección de atributos

**`trait_multiselect`** · 5 % de la sesión · el puente de retrocompatibilidad.

### Qué mide

Qué fracción de la comunidad reconoce cada uno de los **7 atributos originales** del etiquetado
manual del laboratorio. Es lo que permite comparar el modelo nuevo contra el previo manteniendo
constante todo salvo la calidad de la medición.

### Enunciado

```
What does Sett do well?
```

Subtítulo permanente: *"Pick all that apply."*

### Tarjeta

```
┌─────────────────────────────┐
│  What does Sett do well?    │
│  Pick all that apply.       │
│        ┌───────┐            │
│        │ [img] │            │
│        └───────┘            │
│          Sett               │
│  ┌──────────┐ ┌──────────┐  │
│  │ ✓ Engage │ │  Poke    │  │
│  ├──────────┤ ├──────────┤  │
│  │  Pick    │ │  Peel    │  │
│  ├──────────┤ ├──────────┤  │
│  │ Front to │ │ ✓ Dive   │  │
│  │ back     │ │          │  │
│  ├──────────┴─┴──────────┤  │
│  │     Split push        │  │
│  └───────────────────────┘  │
│      ┌───────────────┐      │
│      │   Confirm     │      │
│      └───────────────┘      │
└─────────────────────────────┘
```

Cada atributo tiene su propia definición desplegable, igual que las dimensiones.

### Payload

```jsonc
{ "question_id": 55120, "answer": { "traits": ["engage", "dive"] }, "response_time_ms": 8400 }
```

**`{"traits": []}` es una respuesta válida y significativa**: quiere decir "ninguno de estos". No se
confunde con no haber respondido, porque una no-respuesta no genera fila. Confirmar sin marcar nada
requiere un toque en *Confirm*, así que es deliberado.

### Generación de candidatas

Un campeón activo de un tier habilitado. Una pregunta por (campeón, parche).

### Agregación

Proporción ponderada por trust de respondedores que marcaron cada atributo, con **intervalo de
Wilson**. Se usa Wilson y no el intervalo normal porque con muestras chicas y proporciones cerca de
0 o de 1 —el caso típico de un atributo que casi nadie o casi todos marcan— el intervalo normal
produce extremos fuera de `[0,1]`.

### Los 7 atributos

| `code` | Etiqueta | Definición desplegable |
|---|---|---|
| `engage` | Engage | Starts fights on their own terms. |
| `poke` | Poke | Wears enemies down from range. |
| `pick` | Pick | Catches out and kills isolated targets. |
| `peel` | Peel | Keeps divers off their carries. |
| `front_to_back` | Front to back | Wants a straight teamfight, tanks in front. |
| `dive` | Dive | Jumps past the front line onto the back line. |
| `split_push` | Split push | Pressures a side lane instead of grouping. |

> Cuatro de estos códigos coinciden con nombres de dimensiones del tipo 1, pero **no miden lo
> mismo**: la dimensión es un score relativo de comparación pareada, el atributo es una proporción
> absoluta. En el CSV nunca colisionan porque los atributos llevan prefijo `trait_`
> (ver [`26-esquema-de-salida.md`](26-esquema-de-salida.md) §2.2).

### Casos borde

| Situación | Comportamiento |
|---|---|
| Un atributo se agrega o desactiva | Las respuestas viejas conservan los códigos que tenían; la proporción se calcula sobre las respuestas donde el atributo estaba activo, y `_n` lo refleja |
| Un respondedor marca los 7 | Válido, pero contribuye al patrón de *straightlining* si se repite |
| Código de atributo inexistente en el payload | `400`. La validación de la API cruza contra `traits` activos |

---

## 7. Composición de la sesión

| Tipo | Proporción |
|---|---|
| 1 — pareada por dimensión | 50 % |
| 2 — pico de poder | 20 % |
| 3 — matchup 1v1 | 15 % |
| 3 — matchup 2v2 de bot | 5 % |
| 4 — sinergia de dupla | 5 % |
| 5 — atributos | 5 % |

Reglas que se superponen a esa mezcla:

| Regla | Detalle |
|---|---|
| Arranque | Las **primeras 3 preguntas son siempre de tipo 1**: son las más fáciles de entender sin instrucciones |
| Honeypot | 1 cada 10–15 preguntas, en posición aleatoria dentro de la ventana |
| Retest | 1 cada 30 preguntas, repitiendo una que el mismo respondedor contestó hace 15 o más preguntas |
| Variedad | No más de 3 preguntas seguidas del mismo tipo, para que la sesión no se vuelva monótona |

El detalle del algoritmo que elige *cuál* pregunta dentro de cada tipo está en
[`21-sampler.md`](21-sampler.md).

---

## 8. Orden de implementación

Sigue el valor esperado de lo que produce cada tipo, y coincide con el cronograma del Informe
Inicial. Cada tipo se implementa **completo —de la tabla a la tarjeta— antes de empezar el
siguiente**, de modo que un retraso reduzca la cantidad de tipos terminados y nunca la calidad de
los ya entregados.

| Orden | Tipo | Semana |
|---|---|---|
| 1 | Tipo 1 — pareada por dimensión | 3 |
| 2 | Tipo 2 — pico de poder | 4 |
| 3 | Tipo 3 — matchup 1v1 | 4 |
| 4 | Tipo 3 — matchup 2v2 de bot | 8 |
| 5 | Tipo 4 — sinergia de dupla | 8 |
| 6 | Tipo 5 — atributos | 8 |

La variante 2v2 va junto al tipo 4 y no junto al 1v1 porque comparte con aquél el maquetado de
duplas apiladas y la lógica de generación de candidatas: implementarlos juntos evita hacer dos veces
el mismo trabajo de interfaz.
