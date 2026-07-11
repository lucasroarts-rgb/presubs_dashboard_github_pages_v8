$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$TaskName = "PreSubs Dashboard Daily Sync 06h"
$BatPath = Join-Path $Root "AUTOMATIZAR_DIARIO.bat"

Write-Host ""
Write-Host "Schedule the daily PreSubs automation" -ForegroundColor Cyan
Write-Host ""

$timeInput = Read-Host "Execution time every day [06:00]"
if ([string]::IsNullOrWhiteSpace($timeInput)) { $timeInput = "06:00" }

try {
    $time = [datetime]::ParseExact($timeInput, "HH:mm", $null)
} catch {
    throw "Use the HH:mm format, for example 06:00."
}

$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$BatPath`"" `
    -WorkingDirectory $Root

$trigger = New-ScheduledTaskTrigger -Daily -At $time

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Updates PreSubs Meta data through yesterday, rebuilds the dashboard and publishes GitHub Pages." `
    -Force | Out-Null

Write-Host ""
Write-Host "Scheduled successfully." -ForegroundColor Green
Write-Host "Task: $TaskName"
Write-Host "Every day at $timeInput in the Windows local timezone."
Write-Host "The computer must be on and connected to the internet."
Write-Host ""
