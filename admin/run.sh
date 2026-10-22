#!/usr/bin/env sh
# Levanta el panel de administración en http://127.0.0.1:5000 (ADR-025).
#
# Construye el frontend si falta el build y arranca el backend, que lo sirve. El host lo fija el
# propio paquete (`draftsense_admin.config.HOST`): no hay forma de abrirlo a la red desde acá.
set -eu
cd "$(dirname "$0")"

if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm ci && npm run build)
fi

if [ -x backend/.venv/bin/python ]; then
  PYTHON=backend/.venv/bin/python
else
  PYTHON=backend/.venv/Scripts/python
fi
cd backend && exec "../$PYTHON" -m draftsense_admin
