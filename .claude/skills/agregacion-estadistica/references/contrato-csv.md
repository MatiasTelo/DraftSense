# El contrato de salida

**El contrato columna por columna está en `docs/26-esquema-de-salida.md`**, con un ejemplo ejecutable
en `docs/examples/`. Acá está lo que hay que tener presente antes de tocar una columna. Los `§` sin
prefijo son de `26-esquema-de-salida.md`.

## Los seis CSV (§1)

Desde el 08/10/2026 ([ADR-023](../../../../docs/13-adr/ADR-023-salida-en-formato-largo.md)) el viejo
`champion_features` de 126 columnas son **cuatro archivos en formato largo**, sin `synergy_mean`, y
`duo_features` lleva `role_a` / `role_b` en vez de `duo_context`.

| Archivo | Granularidad | Filas esperadas | Columnas |
|---|---|---|---|
| `champion_dimensions_v<patch>.csv` | (campeón, dimensión): 8 por campeón | 320 a 1 360 | 15 |
| `peak_timing_v<patch>.csv` | un campeón | 40 a 170 | 17 |
| `champion_lane_strength_v<patch>.csv` | (campeón, rol): siempre 3 por campeón | 120 a 510 | 13 |
| `champion_traits_v<patch>.csv` | (campeón, atributo): 7 por campeón | 280 a 1 190 | 13 |
| `matchup_matrix_v<patch>.csv` | (campeón A, campeón B, rol) | ~300 – 2 000 | 12 |
| `duo_features_v<patch>.csv` | (campeón A, campeón B, `role_a`, `role_b`) | ~200 – 1 500 | 19 |
| `data_quality_report_v<patch>.md` | — | — | — |

Tres granularidades: el campeón (cuatro archivos, uno por tipo de pregunta), el par que se
enfrenta, la dupla que juega junta. **Ninguna
medición cae fuera de esas tres, y no se emite nada a nivel de partida** (ADR-005).

`docs/examples/` es además el *fixture* contra el que los tests de exportación comparan las
cabeceras: si cambiás una columna, ese ejemplo cambia también.

## Los conteos que verifica CI

Los cuatro archivos por campeón repiten las 7 columnas de identificación y suman lo propio:
dimensiones 8, pico 10, fuerza de línea 6, atributos 6.

19 magnitudes medidas por campeón: 8 dimensiones + 1 pico + 3 líneas + 7 atributos.

**`infra/check_docs.py` verifica que `26` declare "19 magnitudes" y el conteo de cada archivo en el
encabezado de su sección, y que las cabeceras de `docs/examples/` tengan esos conteos**. Los
números están en `OUTPUT_COLUMNS` y `CHAMPION_MAGNITUDES`. Si agregás o quitás una columna hay que
tocar el documento, el script, `scripts/build_example_exports.py` y regenerar los ejemplos. Si no,
CI falla — que es exactamente lo que tiene que pasar.

## El bloque de sufijos (§2.1)

`snake_case`. Cada magnitud medida lleva un bloque fijo:

| Sufijo | Significado |
|---|---|
| *(ninguno)* | El valor estimado |
| `_ci_low` / `_ci_high` | Extremos del IC al 95 % |
| `_n` | Soporte muestral |
| `_support` | `solid`, `limited` o `insufficient` |

## Las cuatro trampas de lectura

Cada una es un error silencioso: no rompe nada, sólo mete ruido sistemático.

1. **`trait_` no es cosmético** (§2.2). Cuatro atributos del tipo 5 (`engage`, `poke`, `pick`,
   `peel`) se llaman igual que cuatro dimensiones del tipo 1, pero son mediciones distintas y **no
   intercambiables**: la dimensión es un *score relativo* en log-odds sin cero natural
   (*"¿cuánto engage tiene comparado con los demás?"*); el `trait_` es una *proporción absoluta* 0–1
   (*"¿qué fracción de la comunidad dice que hace engage?"*). Un campeón puede tener `engage = -0.4`
   y `trait_engage = 0.71` sin contradicción. **Nunca les quites el prefijo ni las mezcles.**
2. **Vacío no es cero** (§2.3). Celda vacía = "no tenemos datos"; `0` en `engage` = "engage promedio
   del pool". Vacío va con `_n = 0` y `_support = insufficient`.
3. **`_norm` no es comparable entre exports** (§2.5). Su referencia es el mínimo y el máximo del pool
   de esa corrida, que cambia al promover campeones de tier. Para comparar entre parches se usa la
   columna en log-odds. El Informe de Calidad de Datos repite la advertencia.
4. **Los scores están en log-odds centrados en 0 sobre el pool exportado** (§2.5). Una diferencia de
   `+1` significa que la comunidad elige al primero con probabilidad ≈ 0.73.

## `support_level` (§2.4)

Se exporta todo; nada se excluye en silencio. Los umbrales por tipo de magnitud están tabulados en
§2.4 — no los reproduzco acá porque **son la primera calibración y se revisan con los datos del
piloto**; el valor usado en cada corrida queda en `exports`.

Para las dimensiones, `n` cuenta **comparaciones que involucran a ese campeón en esa dimensión**, no
respuestas al par: es la unidad correcta, porque Bradley-Terry estima la fuerza de un campeón a
partir de todas sus comparaciones, vengan del par que vengan.

## El filtro de confianza (§2.6)

Las respuestas con `trust_score < 0.30` y las de respondedores `is_flagged` no entran en la
agregación. **Nunca se borran de `responses`**: el umbral es un parámetro de la corrida y queda
registrado en `exports.min_trust_applied`, así el laboratorio puede pedir un reanálisis con otro
umbral. Es la misma clave de `app_settings` que usa el leaderboard
([ADR-014](../../../../docs/13-adr/ADR-014-leaderboard-filtra-por-confianza.md)) — no una copia.
