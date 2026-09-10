# ADR-016 — La carga inicial del pool aplica la misma regla que la promoción

> Estado: **aceptada** · Fecha: 09/09/2026

## Contexto

[ADR-006](ADR-006-pool-escalonado-por-pick-rate.md) decidió que el pool sería escalonado y que su
composición saldría de un snapshot manual de pick rate, y estimó los tamaños entre paréntesis:
tier 1 «~40», tier 2 «~80», tier 3 el resto. [`21-sampler.md`](../21-sampler.md) §7.1 fijó después
la regla numérica, pero **sólo para la promoción entre parches**: un campeón de tier 2 sube a
tier 1 si entra al top 12 de su rol, y uno de tier 1 baja a tier 2 si cae fuera del top 20.

Al cargar el primer snapshot apareció el hueco: todos los campeones arrancan en tier 3, que es el
default de la columna, y **ninguna regla dice qué pasa la primera vez**. Sin resolverlo, el pool
habilitado queda vacío y el sampler no puede generar ni una pregunta.

Al aplicar §7.1 sobre el snapshot real de 16.17 aparece además una contradicción con las cifras de
ADR-006:

| Corte | Campeones únicos |
|---|---|
| Top 12 de cada rol | **58** — ADR-006 estimaba ~40 |
| Top 20 de cada rol (acumulado) | **96** — ADR-006 estimaba ~80 |

La diferencia sale de que los cinco roles casi no se superponen en sus primeros puestos: 5 × 12 son
60 lugares y sólo dos campeones repiten.

## Decisión

**La carga inicial usa los mismos cortes que la promoción**, aplicados sobre el snapshot completo
en vez de sobre el tier previo:

| Condición sobre `rank_in_role` | `pool_tier` |
|---|---|
| Entra al top 12 de al menos un rol | 1 |
| Entra al top 20 de al menos un rol | 2 |
| El resto, y los que no aparecen en el snapshot | 3 |

Los tamaños que resultan —**58 y 96**— son el dato, y reemplazan a las estimaciones de ADR-006.

## Alternativas consideradas

- **Ajustar los cortes a los tamaños de ADR-006** (top 8 y top 16 por rol, que dan ~40 y ~80). Es
  lo que preserva el argumento estadístico de aquel ADR: con 58 campeones hay 1 653 pares posibles
  por dimensión contra 780 con 40, y el piloto reparte la misma muestra sobre el doble de pares.
  Se descartó porque **introduce dos números nuevos que ningún documento justifica**, sólo para
  hacer coincidir el resultado con un paréntesis. El 12 y el 20 de §7.1 están razonados —la
  histéresis entre ambos evita que un campeón oscile de tier entre parches consecutivos— y el ~40
  de ADR-006 nunca lo estuvo: era una estimación previa a tener el snapshot.
- **Marcar el tier 1 a mano.** Contradice de frente a ADR-006, que puso el pool en datos
  versionados justamente para que no fuera un juicio del administrador.
- **Dejar todo en tier 3 y habilitar los tres tiers.** Es lo más simple y lo peor: reparte la
  muestra del piloto sobre los 173 campeones del catálogo, que es exactamente el escenario que
  ADR-006 existe para evitar.

## Consecuencias

- **El intercambio de ADR-006 se debilita, y hay que saberlo.** El pool es 45 % más grande de lo
  estimado, así que a igual cantidad de respuestas los intervalos de confianza salen más anchos.
  Es un costo aceptado a cambio de que el pool se derive de una regla escrita y de un dato
  versionado, sin números elegidos para que las cuentas cierren.
- El criterio de habilitación del tier 2 (`21-sampler.md` §7.2) **no cambia** y sigue siendo el que
  protege la densidad: mientras la mediana de `D_n` no llegue a 25 y el grafo no esté conectado en
  6 de las 8 dimensiones, el tier 2 no se habilita. Con un núcleo de 58 es todavía más improbable
  que se cumpla, que es el comportamiento correcto.
- Si al cierre del piloto la cobertura resulta demasiado rala, la palanca ya existe y es un dato:
  subir los cortes en un snapshot nuevo y dejar que §7.1 baje campeones a tier 2. No hace falta
  desplegar código ni escribir otro ADR.
- Las cifras «~40» y «~80» de ADR-006 quedan **sin efecto**. El ADR no se edita —el registro es
  histórico— pero al leerlo hay que tomar esos paréntesis como lo que eran: una estimación anterior
  al primer snapshot.
