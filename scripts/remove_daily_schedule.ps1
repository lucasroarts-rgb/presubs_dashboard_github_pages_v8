$ErrorActionPreference = "SilentlyContinue"
$TaskName = "PreSubs Dashboard Daily Sync 06h"
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host ""
Write-Host "Daily PreSubs automation removed."
Write-Host ""
