# Levanta el panel de administración en http://127.0.0.1:5000 (ADR-025).
#
# Construye el frontend si falta el build y arranca el backend, que lo sirve. El host lo fija el
# propio paquete (`draftsense_admin.config.HOST`): no hay forma de abrirlo a la red desde acá.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path 'frontend\dist\index.html')) {
    Push-Location frontend
    npm ci
    npm run build
    Pop-Location
}

Set-Location backend
& '.venv\Scripts\python.exe' -m draftsense_admin
