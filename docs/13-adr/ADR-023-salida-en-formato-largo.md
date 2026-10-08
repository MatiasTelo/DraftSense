# ADR-023 — La salida por campeón se entrega en formato largo, en cuatro archivos

> Estado: **aceptada** · Fecha: 08/10/2026 · Sustituye en parte a
> [ADR-005](ADR-005-alcance-medicion-de-campeones.md): la lista de archivos y la métrica de impacto

## Contexto

Hasta acá, `champion_features.csv` tenía **una fila por campeón y 126 columnas**: las ocho
dimensiones, las tres fuerzas de línea y los siete atributos iban "a lo ancho", con un bloque de
cinco a siete columnas por cada uno. En la reunión del lunes 05/10/2026, Marinozi pidió partirlo
para que el laboratorio pueda **filtrar por dimensión, por rol o por atributo** sin tener que
conocer los nombres de 126 columnas:

1. Un archivo para el **tipo 1**, con una fila por dimensión: cada campeón aparece ocho veces.
2. Un archivo para el **tipo 3** (`lane_strength`), con el rol en una columna aparte: tres filas
   por campeón.
3. Un archivo para el **tipo 5** (`trait_T`), con el atributo en una columna aparte: siete filas por
   campeón.

Además pidió **sacar `synergy_mean`**, conservar `matchup_matrix` tal como está y, en
`duo_features`, **reemplazar `duo_context` por dos columnas con el rol de cada campeón**.

## Decisión

**La salida son seis archivos más el Informe de Calidad de Datos:**

| Archivo | Granularidad |
|---|---|
| `champion_dimensions_v<patch>.csv` | (campeón, dimensión): 8 filas por campeón |
| `champion_lane_strength_v<patch>.csv` | (campeón, rol): siempre 3 filas por campeón, `top`, `mid` y `adc` |
| `champion_traits_v<patch>.csv` | (campeón, atributo): 7 filas por campeón |
| `peak_timing_v<patch>.csv` | campeón: 1 fila por campeón |
| `matchup_matrix_v<patch>.csv` | sin cambios |
| `duo_features_v<patch>.csv` | `duo_context` → `role_a`, `role_b` |

- Los cuatro archivos por campeón llevan las mismas **siete columnas de identificación** que tenía
  `champion_features`, así cada uno se puede usar solo.
- El pico de poder (tipo 2) no estaba en el pedido y queda en un **cuarto archivo**, con una fila por
  campeón y sus diez columnas sin cambios.
- En `champion_lane_strength`, un rol que el campeón no juega **sigue teniendo su fila**, con la
  magnitud vacía, `_n = 0` e `insufficient`, como pide
  [ADR-011](ADR-011-support-level-en-vez-de-excluir.md).
- `synergy_mean` se elimina. La sinergia se mide por dupla y vive sólo en `duo_features`.
- En `duo_features`, `role_a` es el rol que juega `champion_a` en la dupla y `role_b` el de
  `champion_b`. Se mantiene la forma canónica `a_id < b_id`.
- **La métrica de impacto pasa a ser: 19 magnitudes continuas por campeón —8 dimensiones, 1 pico de
  poder, 3 fuerzas de línea y 7 atributos—, todas con intervalo de confianza y soporte muestral,
  versionadas por parche, frente a 7 etiquetas binarias de un anotador único.** Ya no se declara un
  conteo de columnas, porque en formato largo no es una medida del contenido.

## Alternativas consideradas

- **Mantener el archivo ancho y agregar los largos como conveniencia.** Duplica cada número en dos
  archivos y deja la puerta abierta a que diverjan. El pedido fue reemplazarlo.
- **Un único archivo largo con columnas `magnitude` y `key`.** Mezclaría unidades distintas
  (log-odds, minutos, proporciones) en la misma columna de valor, y para el tipo 2 la clave no
  significa nada.
- **Meter el pico de poder en el archivo de dimensiones**, como si fuera una novena dimensión. Es una
  magnitud en minutos, no un score de Bradley-Terry, y además trae cinco columnas `power_at_*` que en
  las otras filas quedarían vacías.
- **Dejar `duo_context` y agregar los roles.** Sería redundante: el contexto se deduce del par de
  roles.

## Consecuencias

- En los archivos largos el prefijo `trait_` deja de hacer falta: dimensiones y atributos viven en
  archivos distintos y sus columnas de valor tienen nombres distintos (`score` contra `proportion`).
  La advertencia conceptual de [`26-esquema-de-salida.md`](../26-esquema-de-salida.md) §2.2 sigue
  en pie: `engage` como dimensión y `engage` como atributo no son la misma medición.
- `infra/check_docs.py` deja de verificar "126 columnas" y "20 magnitudes", y pasa a verificar
  "19 magnitudes" y la cantidad de columnas de cada archivo.
- `scripts/build_example_exports.py` y [`examples/`](../examples/) se regeneran con las cabeceras
  nuevas.
- El CHECK `exports_kind_valid` cambia en la migración `0004`.
- La tabla `aggregates` conserva `duo_ctx`: es una caché interna y el par de roles se deriva de él al
  exportar.
- **ADR-005 sigue vigente en lo que importa**: DraftSense mide campeones y la frontera es el CSV.
  Cambian sólo la cantidad de archivos y la forma de la métrica. Esto, junto con el desvío del
  `match_features.csv`, hay que registrarlo en el Informe de Avance.
