# ADR-002 — `responses` es append-only

> Estado: **aceptada** · Fecha: 31/08/2026

## Contexto

Las respuestas crudas son el activo irremplazable del proyecto: se recolectan una sola vez, de
usuarios anónimos que no van a volver, durante una ventana de pocas semanas. Todo lo demás
—agregados, features, informes— se puede recalcular; una respuesta borrada está perdida.

Al mismo tiempo el sistema detecta continuamente respuestas de baja calidad: honeypots fallados,
inconsistencias en el test-retest, respuestas más rápidas de lo que lleva leer la pregunta. La
reacción instintiva sería borrarlas.

## Decisión

`responses` es **append-only**. Una respuesta nunca se modifica ni se borra. Las correcciones de
calidad se aplican como **pesos** en la agregación y como **filtros parametrizados** en el export,
nunca tocando el crudo.

Se garantiza con permisos de Postgres, no con disciplina del código: el rol `draftsense_app` tiene
`INSERT` y `SELECT` sobre `responses`, y se le revoca explícitamente `UPDATE`, `DELETE` y `TRUNCATE`.

## Alternativas consideradas

- **Borrar las respuestas de baja calidad.** Simplifica la agregación, pero congela para siempre un
  criterio de calidad que todavía no está calibrado: los umbrales del trust score son una primera
  estimación y se revisan con los datos reales del piloto. Borrar hoy con un umbral que mañana
  resulta mal elegido es irreversible.
- **Borrado lógico con `is_deleted`.** Equivalente en efecto pero peor en forma: invita a que cada
  consulta se olvide del filtro, y el permiso de `UPDATE` abre la puerta a modificar el `answer`.

## Consecuencias

- **La validación tiene que ser hermética en el `INSERT`.** Un dato mal formado no se puede
  arreglar después, y por eso las restricciones de forma del `answer` viven en la base como
  `CHECK` de tabla y no sólo en Pydantic.
- El umbral de confianza es un **parámetro de la corrida**, registrado en `exports.min_trust_applied`.
  Si el laboratorio quiere reanalizar con otro criterio, los datos están.
- `aggregates` es caché pura: se puede truncar y reconstruir enteramente desde `responses`.
- La tabla crece monótonamente. Con ~250 B por fila y una meta de miles de respuestas, es
  irrelevante frente a los 500 MB del plan gratuito.
