"""La lógica del sistema.

Un service recibe una `AsyncSession` y tipos del dominio, y **no importa nada de `fastapi`**:
esa es la regla que mantiene la lógica probable sin levantar HTTP y reutilizable desde los jobs
de fondo y el pipeline. Ver ADR-015.
"""
