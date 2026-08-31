# ADR-004 — Versionado por parche en el crudo, ventana con decaimiento en la agregación

> Estado: **aceptada** · Fecha: 31/08/2026

## Contexto

*League of Legends* recibe cambios de balance cada dos semanas. Un campeón puede cambiar
sustancialmente entre parches, así que una respuesta sólo tiene sentido junto al parche en que se
dio. Esa es una de las cuatro limitaciones del etiquetado actual que el proyecto viene a resolver.

Pero el piloto dura unas cuatro semanas y por lo tanto **cruza dos o tres parches**. Agregar por
parche estricto partiría la muestra en cohortes de unos pocos cientos de respuestas cada una,
insuficientes para estimar nada con precisión útil. La solución al problema metodológico crearía un
problema estadístico peor.

## Decisión

Se separan las dos cosas:

- **El crudo se versiona por parche, siempre.** Cada fila de `responses` lleva su `patch_id` y nunca
  lo pierde.
- **La agregación corre sobre una ventana de parches**, ponderando cada respuesta por recencia con
  un decaimiento exponencial de vida media configurable:

  ```
  peso_recencia(r) = 0.5 ^ (dias_desde(r) / vida_media)
  peso_total(r)    = peso_recencia(r) · trust_score(respondedor)
  ```

La ventana y la vida media son parámetros de cada corrida y quedan registrados en
`exports.patch_window` y `exports.decay_halflife_days`.

## Alternativas consideradas

- **Agregar por parche estricto.** Metodológicamente impecable, estadísticamente inservible con el
  volumen del piloto: sólo el parche con más datos produciría un CSV utilizable y los demás
  quedarían sin soporte.
- **Declarar una cohorte única de piloto** e ignorar los cambios de parche dentro de ella. Más
  simple, pero pierde la trazabilidad temporal y no escala: en cuanto el laboratorio siga
  recolectando, el problema vuelve.
- **Descartar las respuestas de parches anteriores.** Tirar datos escasos para ganar pureza es
  exactamente el intercambio equivocado en un proyecto cuyo cuello de botella es el volumen.

## Consecuencias

- Un parche nuevo **no invalida datos**: los respondedores de parches previos siguen aportando, con
  menos peso.
- Un `champion_features_v16.20.csv` puede contener respuestas de 16.18 y 16.19. La columna
  `patch_window` lo dice explícitamente y el Informe de Calidad de Datos lo repite.
- La elección de la vida media es un juicio, no un hecho. Se calibra con los datos del piloto y se
  reporta; un valor demasiado corto desperdicia muestra, uno demasiado largo mezcla campeones que
  ya cambiaron.
- Se puede reprocesar con otra ventana en cualquier momento, porque el crudo conserva el `patch_id`.
