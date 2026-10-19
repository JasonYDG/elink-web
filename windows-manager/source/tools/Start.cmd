@echo off
setlocal
cd /d "%~dp0"
if not exist "app\ElinkManager.exe" (
    echo ERROR: app\ElinkManager.exe is missing.
    echo Extract the complete ZIP before running Start.cmd.
    echo Press any key to close this window.
    pause >nul
    exit /b 2
)
set "elink_log_dir=%LOCALAPPDATA%\ElinkManager\logs"
if not defined LOCALAPPDATA set "elink_log_dir=%TEMP%\ElinkManager\logs"
if not exist "%elink_log_dir%" mkdir "%elink_log_dir%" 2>nul
if not exist "%elink_log_dir%" (
    echo ERROR: Cannot create the startup log directory.
    echo Press any key to close this window.
    pause >nul
    exit /b 3
)
echo Starting Elink Manager. Keep this window open.
echo Startup log: "%elink_log_dir%\startup.log"
"app\ElinkManager.exe" --open %* >>"%elink_log_dir%\startup.log" 2>&1
set "elink_exit=%errorlevel%"
if "%elink_exit%"=="0" exit /b 0
echo.
echo ERROR: Elink Manager stopped with exit code %elink_exit%.
echo If an older manager is running on port 18765, close its console first.
echo Closing only the browser tab does not stop the old manager.
echo See the startup log above for the full error.
echo Press any key to close this window.
pause >nul
exit /b %elink_exit%
