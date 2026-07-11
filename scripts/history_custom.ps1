$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "Import historical PRESUBS data" -ForegroundColor Cyan
Write-Host "The dashboard uses complete Friday-to-Thursday periods." -ForegroundColor DarkGray
Write-Host ""

$start = Read-Host "Start date (YYYY-MM-DD)"
$end = Read-Host "End date (YYYY-MM-DD, leave blank for last completed Thursday)"

$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "run_history.ps1"),
    "-Start", $start
)
if ($end) {
    $arguments += @("-End", $end)
}

& powershell.exe @arguments
exit $LASTEXITCODE
