$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "Update a specific Meta reporting period" -ForegroundColor Cyan
Write-Host ""

$start = Read-Host "Start date (YYYY-MM-DD)"
$end = Read-Host "End date (YYYY-MM-DD)"

& powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File (Join-Path $PSScriptRoot "run_automation.ps1") `
    -Start $start `
    -End $end

exit $LASTEXITCODE
