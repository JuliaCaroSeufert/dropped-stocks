# uninstall_task.ps1
# Run this to stop and remove the daily scheduled task.

$taskName = "DroppedStocksAlert"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Task '$taskName' removed. The daily check will no longer run."
} else {
    Write-Host "Task '$taskName' was not found — nothing to remove."
}
