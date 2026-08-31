# ADR-008 — Conectividad del grafo por chequeo de componentes, sin campeones ancla

> Estado: **aceptada** · Fecha: 31/08/2026

## Contexto

Bradley-Terry estima la fuerza de cada competidor a partir de comparaciones parciales, pero necesita
que el **grafo de comparaciones esté conectado**: si los campeones se parten en dos grupos que nunca
se compararon entre sí, no hay forma de ubicar un grupo respecto del otro y el modelo no tiene
solución única.

El sampler prioriza escasez y entropía. Nada en esa función de prioridad garantiza conectividad; de
hecho, la entropía empuja a insistir sobre pares disputados, que tienden a estar dentro de un mismo
grupo de campeones parecidos. El riesgo es real, no teórico.

## Decisión

Un job horario, `check_graph_connectivity`, calcula las **componentes conexas del grafo de
comparaciones por dimensión**. Cuando detecta más de una componente, marca `bridge_priority = true`
en las preguntas que unirían componentes separadas, y el sampler las trata como prioridad máxima
por encima de escasez y entropía.

No se designan campeones ancla.

## Alternativas consideradas

- **Campeones ancla.** Un conjunto de ~12 campeones por rol que se comparan contra todos, formando
  un grafo estrella conectado por construcción. Converge más rápido, pero **introduce un sesgo de
  diseño**: los anclas acumulan muchísimas más comparaciones que el resto, sus scores quedan con
  intervalos artificialmente angostos, y todo el ordenamiento pasa a depender de una elección
  arbitraria hecha antes de tener datos. En un instrumento cuyo objetivo es reportar confiabilidad,
  meter una asimetría deliberada en el muestreo es difícil de defender.
- **Bradley-Terry regularizado con prior bayesiano (MAP).** Siempre devuelve una solución, aun con
  el grafo partido. Pero los scores entre componentes desconectadas no son realmente comparables:
  el prior los ubica, no los datos. Convierte un problema visible en uno invisible.

## Consecuencias

- El muestreo permanece **simétrico**: ningún campeón recibe atención privilegiada por decisión
  previa, y los intervalos de confianza reflejan la evidencia real.
- La conectividad se alcanza **más lento** que con anclas. Es el costo aceptado, y el job lo mitiga
  atacando el problema exactamente donde aparece.
- El estado de conectividad por dimensión es **observable**: se muestra en el panel de
  administración y se reporta en el Informe de Calidad de Datos.
- Si al cierre del piloto alguna dimensión queda con el grafo partido, se reporta como tal y esos
  scores se marcan `insufficient`. La regularización bayesiana queda como red de seguridad
  documentada, nunca como plan principal.
