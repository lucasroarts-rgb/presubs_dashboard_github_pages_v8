$TaskName = "PreSubs Dashboard Weekly Sync"
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "Weekly PreSubs automation removed." -ForegroundColor Yellow
Write-Host ""
