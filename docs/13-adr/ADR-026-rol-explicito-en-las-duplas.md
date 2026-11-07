# ADR-026 — Cada pregunta de duplas guarda qué rol juega cada campeón

> Estado: **aceptada** · Fecha: 29/10/2026

## Contexto

La variante 2v2 del tipo 3 y el tipo 4 comparan **duplas**: un `adc` con un `support`, un `top` con
un `jungle` o un `mid` con un `jungle` ([`20-tipos-de-pregunta.md`](../20-tipos-de-pregunta.md) §4.2
y §5). El esquema de la semana 1 guarda esas preguntas con los cuatro campeones en forma canónica
(`champion_a < champion_b`, `champion_c < champion_d`, `champion_a < champion_c`) y el contexto en
`duo_ctx`, pero **no guarda qué campeón juega qué rol**: el orden canónico es por id y borra esa
información.

La salida sí la necesita. Desde [ADR-023](ADR-023-salida-en-formato-largo.md), `duo_features` lleva
`role_a` y `role_b`, y [`25-agregacion.md`](../25-agregacion.md) §5.5 dice que el rol **sale de la
pregunta, no de `champions.roles`**: un campeón que juega adc y support puede aparecer en las dos
posiciones de distintas duplas.

Deducirlo de `champions.roles` alcanza sólo cuando cada integrante tiene uno solo de los dos roles
del contexto. En el snapshot de pick rate del 16.17 ([ADR-019](ADR-019-roles-derivados-del-snapshot.md))
hay ocho campeones con los dos roles de un mismo contexto: Xerath y Seraphine (`adc` y `support`),
Cho'Gath (`top` y `jungle`), y Sylas, Qiyana, Ekko, Diana y Zed (`mid` y `jungle`). Una dupla
Xerath + Seraphine es ambigua, y el rol que el pipeline le asignara podría no ser el que vio quien
respondió.

## Decisión

**`questions` guarda el rol de cada campeón en cuatro columnas nuevas, `role_a`, `role_b`, `role_c`
y `role_d`, del tipo `lane_role`** (migración `0006`).

1. **Obligatorias en las preguntas de duplas** —`lane_matchup` con `duo_ctx = 'bot'` y
   `duo_synergy`— y **nulas en todas las demás**. El `CHECK questions_shape` lo exige, igual que
   ya exige el resto de los campos por tipo.
2. **Cada dupla tiene exactamente los dos roles de su contexto**, en cualquier orden: `{adc,
   support}` en `bot`, `{top, jungle}` en `top_jungle`, `{mid, jungle}` en `mid_jungle`. También
   lo verifica el `CHECK`.
3. **El orden canónico no cambia.** Los roles viajan con su campeón: `role_a` es el de
   `champion_a`, sea cual sea.
4. **Los roles entran en la identidad de la pregunta.** Xerath (adc) + Seraphine (support) contra
   una dupla dada y Xerath (support) + Seraphine (adc) contra la misma son dos preguntas distintas.
5. **Al servirla, cada lado lista a sus campeones en el orden de roles del contexto**: primero el
   `adc`, el `top` o el `mid`, después el `support` o el `jungle`. Así la tarjeta muestra siempre
   «Caitlyn + Lux» y nunca «Lux + Caitlyn», y el rol de cada uno queda implícito en la posición.
6. **El generador sortea el rol, no sólo el campeón.** Para cada lugar de la dupla elige entre los
   campeones que tienen ese rol en `champions.roles`. Un campeón con los dos roles puede aparecer
   en cualquiera de los dos lugares, nunca en ambos de la misma dupla (20 §5, casos borde).

## Alternativas consideradas

- **Excluir de las duplas de un contexto a los campeones con sus dos roles.** No necesita
  migración, pero contradice 20 §5, que los admite expresamente, y deja fuera a cinco campeones del
  contexto `mid_jungle`, el más afectado.
- **Deducir el rol en la agregación** desde `champions.roles`, con una regla fija para los casos
  ambiguos. Tampoco necesita migración, pero el rol del CSV podría no ser el de la pregunta que se
  contestó, y `champions.roles` cambia con cada snapshot ([ADR-019](ADR-019-roles-derivados-del-snapshot.md)):
  la misma respuesta saldría con otro rol en una corrida posterior.
- **Abandonar el orden canónico y usar el orden de los lugares** (`champion_a` siempre el adc).
  Cambia el sentido de un `CHECK` que ya rige para el 1v1 y el tipo 1, y no resuelve el caso de
  un campeón que ocupa lugares distintos en duplas distintas.

## Consecuencias

- La migración `0006` agrega las cuatro columnas, rehace el índice de identidad y amplía el
  `CHECK`. No toca filas existentes: ninguna pregunta de duplas se materializó antes de la semana 8.
- El pipeline lee `role_a … role_d` de la pregunta para escribir `role_a` y `role_b` de
  `duo_features`, y ajusta cada contexto con duplas identificadas por (campeón, rol, campeón, rol).
- El espacio de preguntas de duplas crece levemente: una dupla con un campeón ambiguo puede existir
  con dos asignaciones de rol.
