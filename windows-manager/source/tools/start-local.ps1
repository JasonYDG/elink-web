$ErrorActionPreference = 'Stop'
$elinkRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$elinkPython = Join-Path $elinkRoot 'runtime\venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $elinkPython)) { throw 'Use the portable release launcher, or create runtime/venv and install source/backend/requirements.txt first.' }
& $elinkPython (Join-Path $elinkRoot 'source\backend\server.py') --open
