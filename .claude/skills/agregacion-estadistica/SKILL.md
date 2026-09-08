---
name: agregacion-estadistica
description: >-
  El pipeline de agregación estadística de DraftSense: convierte respuestas crudas en los tres CSV
  que recibe el Laboratorio DHARMa. Usar SIEMPRE al trabajar sobre el paquete `aggregation/`, sobre
  `docs/25-agregacion.md`, `docs/26-esquema-de-salida.md` o `docs/27-validacion-confiabilidad.md`, y
  ante cualquier tarea de ingeniería o ciencia de datos del proyecto. Activar con: Bradley-Terry,
  `choix`, ILSR, iteración MM de Hunter, Rao-Kupper, bootstrap, intervalo de confianza, intervalo de
  Wilson, alfa de Krippendorff, mediana ponderada, trust score como peso, decaimiento por recencia,
  ventana de parches, conectividad del grafo de comparaciones, `champion_features`, `matchup_matrix`,
  `duo_features`, `_support`, `_n`, `power_at_*`, `peak_minute`, `synergy`, `lane_strength`,
  reproducibilidad, SHA-256 de una exportación, o el Informe de Calidad de Datos. Complementa a
  `draftsense` (alcance) y a `draftsense-backend` (el código que persiste las respuestas): las
  fórmulas se leen de la documentación, esta skill dice dónde están y qué no se puede romper.
---

# Agregación estadística

Del respondedor al CSV. Es la parte menos estándar del proyecto y la que más fácil se rompe en
silencio: un error acá no tira una excepción, produce un número plausible y equivocado.

## Estado

**`aggregation/` está vacía.** El paquete se implementa en la **semana 9** (27/10 – 02/11) según
`docs/25-agregacion.md` §8. `docs/27-validacion-confiabilidad.md` está **pendiente** y desbloquea la
semana 10: hay que escribirlo antes de implementar la validación de confiabilidad.

La especificación en cambio está completa y en `v1`: `25-agregacion.md` (52 KB, el documento más
grande del repo) y `26-esquema-de-salida.md`, más el ejemplo ejecutable de `docs/examples/`.

## La corrida

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

Todo parámetro omitido se toma de `app_settings` (prefijo `aggregation.`, tabla en §9), y **el valor
efectivamente usado —no el default— es el que se registra** en `exports`.

`--exported-at` es un parámetro y no `now()` porque la fecha entra en la columna `exported_at` de
cada fila: sin ella, reproducir una corrida otro día daría otro archivo.

Los ocho pasos de una corrida están en §8.2. Los **15 ajustes** —8 dimensiones, 3 roles del 1v1, el
2v2 de bot y los 3 contextos de sinergia— son independientes y corren en paralelo.

## Lo que no se puede romper

1. **La reproducibilidad es un criterio de aceptación** (CA-408): dos corridas con los mismos
   parámetros sobre el mismo crudo deben dar un SHA-256 idéntico. Se apoya en cinco cosas, y
   aflojar cualquiera la rompe **sin que falle nada**. Ver `references/reproducibilidad.md`.
2. **El peso es la única ponderación del pipeline**:
   `peso(r) = trust_score(respondedor) · 0.5 ^ (dias(r) / H)`. No agregues otro factor. El rol, el
   rango y las horas declaradas **no ponderan** — sus cinco usos legítimos están en §3.
3. **Re-centrar dentro de cada iteración del bootstrap.** Sin eso, la indeterminación aditiva de
   Bradley-Terry se cuela en la distribución y todos los intervalos salen inflados por una varianza
   que no existe. Es el error clásico al bootstrapear BT.
4. **Vacío no es cero.** Una magnitud sin datos es celda vacía, `_n = 0`, `_support = insufficient`
   ([ADR-011](../../../docs/13-adr/ADR-011-support-level-en-vez-de-excluir.md), CA-405).
5. **Si ninguna respuesta pasa los filtros, la corrida falla y no escribe archivos.** Un CSV de 0
   filas con su SHA-256 registrado sería peor que no tener corrida.
6. **Honeypots y retests no entran a la agregación** (§1.3). Sirven para calcular el trust score, que
   ya viaja en el peso; contarlos otra vez sería usar el mismo dato dos veces.

## Cuándo leer cada referencia

- **`references/estimadores.md`** — al implementar o revisar cualquier estimador. Dice cuál va con
  qué tipo de pregunta y en qué sección está su fórmula.
- **`references/reproducibilidad.md`** — al tocar el orden de una consulta, el formato de un número,
  la semilla o el bootstrap. Es donde vive CA-408.
- **`references/contrato-csv.md`** — al agregar, quitar o renombrar una columna. Los conteos los
  verifica CI.

## Casos límite

Están tabulados en `docs/25-agregacion.md` §7: grafo desconectado, campeón con una sola comparación,
todas las respuestas `even`, dimensión desactivada a mitad de ventana, contexto de dupla sin
respuestas, más del 5 % de remuestreos descartados. **Leé esa tabla antes de inventar un
comportamiento para un caso raro** — casi seguro ya está decidido.

## Un límite conocido, ya documentado

El bootstrap es **sobre las comparaciones**, no por respondedor, así que supone independencia entre
comparaciones que no es del todo cierta: los intervalos publicados son algo más angostos que los
honestos (§4.7). La resolución ya está pautada: la corrida calcula las dos versiones, el Informe de
Calidad de Datos reporta ambos anchos, y **si el decil más activo aporta más del 40 % de las
comparaciones, corresponde un ADR** que reemplace lo fijado en `26-esquema-de-salida.md` §3.2. Se
decide en la semana 10, con los datos del piloto. **No lo cambies antes ni por tu cuenta.**

## Mantener esta skill al día

Si cambian `docs/25-agregacion.md`, `docs/26-esquema-de-salida.md` o
`docs/27-validacion-confiabilidad.md` —sobre todo su numeración de secciones—, corregir las
referencias de acá. Cuando `27` pase de `pendiente` a `v1`, actualizar el estado y sumar sus
secciones a `estimadores.md`.
