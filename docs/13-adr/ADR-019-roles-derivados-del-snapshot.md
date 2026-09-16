# ADR-019 — Los roles de cada campeón salen del snapshot de pick rate

> Estado: **aceptada** · Fecha: 16/09/2026

## Contexto

`champions.roles` es la columna que decide qué enfrentamientos de línea existen: el tipo 3 sólo
empareja campeones que comparten un rol en `top`, `mid` o `adc`
([`21-sampler.md`](../21-sampler.md) §2.3), y el tipo 4 de la semana 8 arma duplas con ella.

Hasta ahora esa columna tenía **roles provisorios**. Data Dragon no clasifica por carril sino por
clase (Marksman, Tank, Mage…), y `seed-champions` traduce clase a carril con un mapa fijo para que
cada fila cumpla `champions_has_roles` desde la primera carga. El comentario del seeder decía que el
snapshot de pick rate «pisa estos valores al cargarse», pero **el código nunca lo hizo**:
`seed-pick-rate` asignaba el `pool_tier` y dejaba los roles como estaban.

Contrastado contra el snapshot de lolalytics del parche 16.17, el mapa provisorio es incorrecto para
**38 de los 58 campeones del tier 1** y para 90 de los 131 que aparecen en el snapshot:

| Rol | Campeones del tier 1 según el snapshot | Según el mapa provisorio |
|---|---|---|
| `top` | 13 | 25 |
| `jungle` | 13 | 0 |
| `mid` | 13 | 34 |
| `adc` | 16 | 15 |
| `support` | 12 | 13 |

Lee Sin figuraba como mid y top; Graves, como adc. Con esos roles el tipo 3 preguntaría por
enfrentamientos que nadie juega, y la respuesta más honesta sería ruido.

## Decisión

**`champions.roles` es el conjunto de roles en los que el campeón aparece en el último snapshot de
pick rate del parche**, ordenados por el valor del enum igual que los provisorios. El snapshot
captura los 30 primeros por rol, así que un campeón tiene un rol cuando está entre los 30 más
elegidos de ese carril.

- Los campeones que **no aparecen** en el snapshot conservan los roles que tenían. Quedan en
  tier 3 ([ADR-016](ADR-016-carga-inicial-del-pool.md)), fuera del pool habilitado, así que sus
  roles no generan preguntas.
- Lo aplica `seed-pick-rate` al cargar un snapshot nuevo, y el comando `sync-roles` sobre un
  snapshot que ya está en la base —que es el caso del 16.17, cargado antes de esta decisión—.
- `seed-champions` sigue sin tocar `roles`: un re-seed desde Data Dragon no debe deshacer lo que
  puso el snapshot.
- Las preguntas ya generadas conservan el rol con el que se crearon
  ([`20-tipos-de-pregunta.md`](../20-tipos-de-pregunta.md) §4.3).

## Alternativas consideradas

- **Contar un rol sólo si el campeón está en el top 12 o en el top 20 de ese carril.** Deja afuera
  los roles secundarios poco elegidos, pero mezcla dos preguntas distintas —si el campeón está en
  el pool y en qué carriles se juega— y reduce los pares posibles del 1v1 justo donde el pool ya es
  chico.
- **Un piso de pick rate** (por ejemplo, 1 % del carril). Es un número nuevo que ningún documento
  justifica, con el mismo defecto que ADR-016 descartó para los cortes de tier.
- **Curación manual en un archivo versionado.** Es la más precisa y la que contradice a
  [ADR-006](ADR-006-pool-escalonado-por-pick-rate.md), que puso el pool en datos medidos para que no
  dependiera del juicio del administrador.
- **Dejar los roles provisorios.** Descartada por los números de arriba.

## Consecuencias

- Aparecen roles de `jungle` y `support` que el mapa provisorio no podía producir, y que el tipo 4
  de la semana 8 necesita.
- Los roles entre los puestos 21 y 30 de un carril pueden generar enfrentamientos poco habituales.
  Si el piloto muestra que esas preguntas tienen una tasa de `even` o de abandono anómala, la
  palanca es un piso de pick rate en un ADR nuevo, no un cambio de código ad hoc.
- Si alguna vez se habilita el tier 3, sus campeones entran con los roles provisorios que tengan.
  Antes de hacerlo, hay que ampliar el snapshot o revisar esos roles.
- Un snapshot nuevo reescribe los roles de los campeones que contiene; los que salen del snapshot
  conservan los del anterior.
