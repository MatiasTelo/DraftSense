"""`python -m draftsense_admin`: levanta el panel en `127.0.0.1` (ADR-025 §1).

Es la única forma documentada de arrancarlo. El host sale de `config.HOST` y no de un argumento,
para que no haya un comando que lo abra a la red del laboratorio.
"""

from __future__ import annotations

import uvicorn

from draftsense_admin.config import HOST, get_admin_settings


def main() -> None:
    settings = get_admin_settings()
    url = f"http://{HOST}:{settings.admin_port}"
    print(f"DraftSense admin en {url}  ({settings.masked_database_url})")
    uvicorn.run("draftsense_admin.main:app", host=HOST, port=settings.admin_port)


if __name__ == "__main__":
    main()
