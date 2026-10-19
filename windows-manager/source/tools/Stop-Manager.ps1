param([ValidateRange(1,65535)][int]$Port = 18765)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
$elinkExit = 2
try {
    $elinkListeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($elinkListeners.Count -eq 0) {
        Write-Host "Elink Manager is not running on port $Port. You can run Start.cmd."
        exit 0
    }
    $elinkOwners = @($elinkListeners | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($elinkOwners.Count -ne 1 -or @($elinkListeners | Where-Object { $_.LocalAddress -ne '127.0.0.1' }).Count -ne 0) {
        throw 'The listener is not one local Elink manager. Nothing was stopped.'
    }
    $elinkBase = "http://127.0.0.1:$Port"
    $elinkConfig = Invoke-RestMethod -Uri "$elinkBase/api/config" -TimeoutSec 5
    if ($elinkConfig.backend -ne 'bleak/windows' -or $elinkConfig.bundled_runtime -ne $true -or $elinkConfig.version -notmatch '^\d+\.\d+\.\d+$') {
        throw 'This service is not a packaged Elink manager. Nothing was stopped.'
    }
    $elinkTarget = Get-Process -Id $elinkOwners[0] -ErrorAction Stop
    $elinkExpected = [IO.Path]::GetFullPath($elinkConfig.runtime_executable)
    if ($elinkTarget.ProcessName -ine 'ElinkManager' -or $elinkTarget.Path -ine $elinkExpected) {
        throw 'The service identity does not match its actual process. Nothing was stopped.'
    }
    $elinkStarted = $elinkTarget.StartTime
    $elinkState = Invoke-RestMethod -Uri "$elinkBase/api/state" -TimeoutSec 5
    if ($elinkState.operation.busy -or $elinkState.operation.scanning -or $elinkState.operation.jobs -ne 0 -or $elinkState.operation.pending_reminders -ne 0) {
        Write-Host 'ERROR: Screen tasks are still pending or running. Nothing was stopped.'
        Write-Host 'Finish the current operation or cancel waiting jobs in the web page, then run Stop.cmd again.'
        exit 3
    }
    $elinkCheck = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    $elinkNow = Get-Process -Id $elinkTarget.Id -ErrorAction Stop
    if ($elinkCheck.Count -ne 1 -or $elinkCheck[0].OwningProcess -ne $elinkTarget.Id -or $elinkNow.StartTime -ne $elinkStarted -or $elinkNow.Path -ine $elinkExpected) {
        throw 'The listener changed during verification. Nothing was stopped.'
    }
    $elinkExit = 4
    Stop-Process -InputObject $elinkTarget -ErrorAction Stop
    if (-not $elinkTarget.WaitForExit(10000)) { throw 'The manager did not exit within 10 seconds.' }
    if (@(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue).Count -ne 0) {
        throw 'The old manager exited, but the port is now used by another process.'
    }
    Write-Host "Stopped Elink Manager $($elinkConfig.version), PID $($elinkTarget.Id). Port $Port is free."
    Write-Host 'You can now run Start.cmd.'
    exit 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    exit $elinkExit
}
