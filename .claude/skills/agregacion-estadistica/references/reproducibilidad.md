# Reproducibilidad — CA-408

**Dos corridas con los mismos parámetros sobre el mismo crudo deben producir un SHA-256 idéntico.**

Es un criterio de aceptación, no una aspiración. Y es frágil de una manera particular: cuando se
rompe, nada falla. Los archivos salen, los números son plausibles, y sólo el hash cambia. Por eso el
test de CA-408 **corre la misma exportación dos veces y compara hashes**.

## Las cinco cosas que la sostienen

Todas están fijadas en `docs/25-agregacion.md`. Aflojar cualquiera la rompe en silencio.

| # | Qué | Dónde | Qué la rompe |
|---|---|---|---|
| 1 | **Orden determinista de la consulta base** | §1.1 | Sacar el `ORDER BY`, o confiar en el orden natural de Postgres |
| 2 | **Semilla derivada de los parámetros**, no del reloj | §4.2 | Un `random.seed()` sin argumento, `time.time()`, o un `set` iterado |
| 3 | **Formato numérico fijo** | §4.6 | Dejar que `str(float)` o pandas decidan los decimales |
| 4 | **Orden de filas fijo** | §4.6 | Ordenar por algo que no sea la clave declarada |
| 5 | **`exported_at` como parámetro**, no `now()` | §8.1 | Tomar la fecha del sistema dentro del pipeline |

La semilla se deriva así:

```
seed = int(sha256(f"{patch_window}|{min_trust}|{H}|{sigma}|{B}|{aggregation_version}")
           .hexdigest()[:16], 16)
```

Si agregás un parámetro que cambia el resultado, **tiene que entrar en esa cadena**.

Hoy la cadena **no** lleva `bt_prior`, las λ de las duplas, `max_iter`, `tol`, los umbrales de
soporte ni el pool: quedan en `exports.params` (el pool, en `pool_champion_ids`), pero dos
corridas que sólo difieren en ellos comparten semilla.

**Qué se puede reproducir y qué no** está en 25 §8.3 (nota del 13/11/2026): la carga lee el
estado actual de la base, así que una corrida vieja se recalcula igual sólo mientras no cambien
el crudo, los trust, los marcados, las honeypots ni el pool. La garantía de una entrega es el
archivo conservado y su SHA-256, no la posibilidad de regenerarlo. CA-408 —dos corridas seguidas,
mismo hash— sigue valiendo.

Tres reglas del 13/11 que cambian bytes y por eso subieron `AGGREGATION_VERSION` a `1.0.1`, o
que hay que conocer antes de tocar `load.py`:

- un valor que redondea a cero se escribe `0.000`, nunca `-0.000` (`writers.number`, 25 §4.6);
- la antigüedad de una respuesta nunca es menor que 0 días (`load.weight`, 25 §2.1);
- el default de `exported_at` es la fecha **UTC**, la misma zona de `created_at`.

## El formato numérico

De §4.6. No es cosmético: de esto depende el hash.

| Qué | Formato |
|---|---|
| Scores en log-odds y sus IC | `%.3f` |
| Proporciones (`proportion`, `_norm`) y sus IC | `%.3f` |
| `unknown_rate` | `%.2f` |
| `power_at_*` | `%.2f` |
| `peak_minute` y su IC | entero |
| `_n` | entero |
| Booleanos | `true` / `false` en minúscula |
| Vacío | cadena vacía |

UTF-8 **sin BOM**, fin de línea `\n`, separador `,`, sin comillas salvo que el valor las necesite.

## El orden de filas

| Archivo | Orden |
|---|---|
| `peak_timing` | `champion_id` |
| `champion_dimensions` | `(champion_id, dimension)`, dimensiones en el orden de 26 §3.2 |
| `champion_lane_strength` | `(champion_id, role)`, en el orden `top`, `mid`, `adc` |
| `champion_traits` | `(champion_id, trait)`, atributos en el orden de 26 §3.5 |
| `matchup_matrix` | `(role, champion_a_id, champion_b_id)` |
| `duo_features` | `(role_a, role_b, champion_a_id, champion_b_id)` |

## El bootstrap

`B = 2 000` remuestreos con reemplazo sobre las comparaciones filtradas, mismo tamaño, mismos pesos.

Tres reglas que no son opcionales:

1. **Centrar `θ_b` dentro de cada iteración.** Sin eso, la indeterminación aditiva del modelo se
   cuela en la distribución y todos los intervalos salen inflados. Es *el* error clásico de
   bootstrapear Bradley-Terry.
2. **Si un remuestreo deja el grafo desconectado en esa dimensión, se descarta y se sortea otro**,
   hasta 3·B intentos. Si se descarta más del **5 %**, la dimensión entera se marca `insufficient` y
   el hecho va al Informe de Calidad de Datos: un intervalo calculado sobre remuestreos
   seleccionados no es un intervalo del 95 %.
3. **Los remuestreos de las 8 dimensiones son independientes.** No se busca un intervalo conjunto:
   cada columna se lee sola.

`IC_95` son los percentiles 2.5 y 97.5.

## El registro de la corrida

Paso 8 de §8.2: **una fila en `exports` por archivo**, con su SHA-256 y **todos** los parámetros —
los efectivamente usados, no los defaults. Es lo que permite reproducir una corrida vieja: se leen
sus parámetros de ahí, incluido `exported_at`, y se vuelven a pasar por CLI.

## Paralelismo

Los 15 ajustes corren en paralelo, y el bootstrap usa **la misma partición de trabajo** (§4.2, paso
5 de §8.2). Si cambiás el esquema de paralelización, cambiás qué números consume cada worker del
generador: el resultado deja de ser reproducible aunque la semilla sea la misma. **La partición es
parte del contrato.**
