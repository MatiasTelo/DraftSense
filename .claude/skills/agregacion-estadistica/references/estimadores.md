# Los cinco estimadores

Uno por tipo de pregunta. **Las fórmulas están en `docs/25-agregacion.md` §5**; acá está el mapa y
las trampas de cada uno. Los `§` sin prefijo son de ese documento.

| Tipo | Pregunta | Estimador | Produce | Dónde |
|---|---|---|---|---|
| 1 | `pairwise_dimension` | Bradley-Terry ponderado | Las 8 dimensiones (7 columnas c/u) | §5.1 |
| 2 | `peak_timing` | Mediana ponderada + curva gaussiana | `peak_minute` y `power_at_*` | §5.2 |
| 3 (1v1) | `lane_matchup` | Modelo ordinal Rao-Kupper | Fuerza de línea y `matchup_matrix` | §5.3 |
| 3 (2v2) | `lane_matchup` | Ídem, sobre duplas | `duo_features.lane_strength` | §5.4 |
| 4 | `duo_synergy` | BT con interacción y penalización L2 | `synergy`, `synergy_mean` | §5.5 |
| 5 | `trait_multiselect` | Proporción con intervalo de Wilson | Los 7 atributos (5 columnas c/u) | §5.6 |

## Tipo 1 — Bradley-Terry por dimensión (§5.1)

Ajustado con `choix.ilsr_pairwise` sobre una matriz densa de comparaciones ponderadas
([ADR-003](../../../../docs/13-adr/ADR-003-bradley-terry.md)). El modelo admite conteos fraccionarios de
forma nativa vía la iteración MM de Hunter (2004), que es lo que permite que el peso de una respuesta
sea un número real y no un conteo.

- `ε = aggregation.bt_prior` (inicial 0.5) es el prior de estabilidad numérica: mantiene finito el
  score de un campeón con una sola comparación y lo encoge hacia 0.
- Los scores salen en **log-odds** y hay que **centrarlos** (el modelo tiene indeterminación
  aditiva). Centrar también dentro de cada iteración del bootstrap.
- Las siete columnas por dimensión están en §5.1 "Las siete columnas".

**Grafo desconectado:** se ajusta una corrida **por componente**, cada una centrada en 0 sobre su
propia componente, y todos los campeones fuera de la componente mayor quedan `insufficient` sin
importar su `_n`. No se inventa un orden global
([ADR-008](../../../../docs/13-adr/ADR-008-conectividad-por-componentes.md), CA-403).

## Tipo 2 — Pico de poder (§5.2)

Mediana ponderada de los minutos declarados, con IC bootstrap. De ahí sale la curva de
[ADR-009](../../../../docs/13-adr/ADR-009-curva-de-poder-gaussiana.md):

```
power_at(t) = exp( -(t - peak_minute)² / (2 · σ²) )
```

`σ = aggregation.power_sigma` (inicial 7.5) es **global**, se calibra con los datos del piloto y se
registra en `exports`. La curva se exporta evaluada en minutos fijos (`power_at_*`), no como función.

## Tipo 3 — Enfrentamiento de línea (§5.3 y §5.4)

Modelo **ordinal de Rao-Kupper**, que es la generalización de Bradley-Terry que admite empates y
margen — la escala de la pregunta tiene cinco niveles, no dos. Los umbrales `τ` capturan el empate:
si todas las respuestas de un par son `even`, `δ ≈ 0` y `τ₁` crece, que es **señal legítima de
matchup equilibrado**, no un error.

`advantage` se lleva del modelo a la escala −1…+1 según §5.3 "del modelo a la escala".

La variante 2v2 (§5.4) corre el mismo modelo sobre duplas y alimenta `duo_features.lane_strength`.

## Tipo 4 — Sinergia (§5.5)

Modelo con término de interacción y **dos penalizaciones L2 distintas**:
`aggregation.duo_lambda_champion` (0.10) sobre los efectos de campeón y
`aggregation.duo_lambda_interaction` (1.00) sobre la interacción. No son la misma constante: la
interacción se penaliza diez veces más.

`synergy_mean` se deriva después (§5.5 "synergy_mean"), no se estima aparte.

**Si un contexto de dupla no tiene ninguna respuesta, no se emite ninguna fila de ese contexto.** No
se predice sobre un modelo que no se ajustó.

## Tipo 5 — Atributos (§5.6)

Proporción de respondedores que marcaron el atributo, con **intervalo de Wilson**. Cinco columnas por
atributo, prefijo `trait_`.

El prefijo no es cosmético: `26-esquema-de-salida.md` §2.2 explica por qué. No lo saques.

## Validación de confiabilidad

Alfa de Krippendorff por dimensión, consistencia test-retest, pass-rate de honeypots, cobertura por
par, ancho medio del intervalo y estabilidad entre segmentos de rango.

**`docs/27-validacion-confiabilidad.md` todavía no está escrito.** Es de la ola 4 y desbloquea la
semana 10. Se redacta **antes** de implementar lo que describe. La estabilidad por segmento de rango
sí está especificada, en §3.5, con sus pisos: `segment_min_respondents` (15) y
`segment_min_comparisons` (300).

## Parámetros

Todos bajo el prefijo `aggregation.` en `app_settings` (RF-606), tabulados en §9, salvo
`export.min_trust` que vive en `22-calidad-de-datos.md` §8. **Ninguno es una constante del código.**

Los cuatro primeros y los umbrales de `_support` **se calibran con los datos del piloto antes de la
entrega final**, así que no los hardcodees ni asumas que los valores iniciales son los definitivos.
