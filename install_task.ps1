# install_task.ps1
# Run this ONCE (as Administrator) to register the daily scheduled task.
# After that it runs every day at 09:00, independent of the console.

$taskName   = "DroppedStocksAlert"
$scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$batFile    = Join-Path $scriptDir "run_daily.bat"
$runAt      = "09:00"   # change this if you prefer a different time

if (-not (Test-Path $batFile)) {
    Write-Error "Could not find run_daily.bat at: $batFile"
    exit 1
}

$action   = New-ScheduledTaskAction `
                -Execute  "cmd.exe" `
                -Argument "/c `"$batFile`""

$trigger  = New-ScheduledTaskTrigger -Daily -At $runAt

# StartWhenAvailable: if the PC was off at 09:00, run as soon as it boots
$settings = New-ScheduledTaskSettingsSet `
                -StartWhenAvailable `
                -DontStopOnIdleEnd `
                -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName  $taskName `
    -Action    $action `
    -Trigger   $trigger `
    -Settings  $settings `
    -RunLevel  Highest `
    -Force | Out-Null

Write-Host ""
Write-Host "Task '$taskName' installed successfully."
Write-Host "It will run every day at $runAt."
Write-Host "If the PC is off at that time it will run the next time it boots."
Write-Host ""
Write-Host "To remove it later, run: .\uninstall_task.ps1"
