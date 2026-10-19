@echo off
setlocal
cd /d "%~dp0"
if not exist "tools\Stop-Manager.ps1" (
    echo ERROR: tools\Stop-Manager.ps1 is missing. Extract the complete ZIP.
    echo Press any key to close this window.
    pause >nul
    exit /b 2
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Stop-Manager.ps1" %*
set "elink_exit=%errorlevel%"
echo Press any key to close this window.
pause >nul
exit /b %elink_exit%
