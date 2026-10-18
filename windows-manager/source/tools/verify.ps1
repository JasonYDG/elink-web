$ErrorActionPreference = 'Stop'
$elinkRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$elinkPython = Join-Path $elinkRoot 'runtime/venv/Scripts/python.exe'
& $elinkPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency gate failed' }
$env:ELINK_TEST_FIRMWARE_DIR = Join-Path $elinkRoot 'build/firmware-1.5.11'
& $elinkPython (Join-Path $elinkRoot 'source/firmware/build.py') --version 1.5.11 --output $env:ELINK_TEST_FIRMWARE_DIR
if ($LASTEXITCODE -ne 0) { throw 'Firmware build failed' }
# OTA tests use the shipped, physically booted 1.0.5 application as the old bank.
& $elinkPython -m unittest discover -s (Join-Path $elinkRoot 'source/tests') -p 'test_*.py' -v
if ($LASTEXITCODE -ne 0) { throw 'Verification failed' }
