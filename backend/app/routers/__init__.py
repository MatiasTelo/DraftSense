"""Los routers: la traducción entre HTTP y el dominio.

Un router declara la ruta, sus parámetros, sus dependencias y su código de estado. No consulta la
base ni toma decisiones de negocio: eso vive en `app/services/`. Ver ADR-015.
"""
