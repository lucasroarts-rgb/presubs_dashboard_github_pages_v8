$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$TaskName = "PreSubs Dashboard Weekly Sync"
$ScriptPath = Join-Path $Root "scripts\run_automation.ps1"

Write-Host ""
Write-Host "Schedule the weekly PreSubs automation" -ForegroundColor Cyan
Write-Host ""

$timeInput = Read-Host "Execution time every Friday [08:00]"
if ([string]::IsNullOrWhiteSpace($timeInput)) { $timeInput = "08:00" }

try {
    $time = [datetime]::ParseExact($timeInput, "HH:mm", $null)
} catch {
    throw "Use the HH:mm format, for example 08:00."
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`"" `
    -WorkingDirectory $Root

$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Friday `
    -At $time

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -Hidden

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Downloads PreSubs Meta data, updates SQLite and publishes GitHub Pages." `
    -Force | Out-Null

Write-Host ""
Write-Host "Scheduled successfully." -ForegroundColor Green
Write-Host "Task: $TaskName"
Write-Host "Every Friday at $timeInput"
Write-Host "The computer must be on and connected to the internet."
Write-Host ""
