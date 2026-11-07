"""El pipeline de agregación de DraftSense: del respondedor a los seis CSV.

La especificación es `docs/25-agregacion.md` (cómo se calcula) y `docs/26-esquema-de-salida.md`
(qué contiene cada columna). Este paquete no la repite: cada módulo cita la sección que implementa.

Una corrida se lanza con `python -m aggregation.run` (§8.1) o desde el panel de administración, y
las dos entradas comparten `pipeline.run`.
"""

from __future__ import annotations

#: Entra en la semilla del bootstrap y en `exports.aggregation_version` (§4.2, CA-407). Cambiarla
#: cambia los números aunque el crudo y los parámetros sean los mismos: subila sólo cuando cambie
#: un estimador, no por un refactor que no toca resultados.
AGGREGATION_VERSION = "1.0.0"
