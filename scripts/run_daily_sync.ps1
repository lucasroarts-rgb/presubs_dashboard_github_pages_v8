$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File (Join-Path $PSScriptRoot "run_automation.ps1") `
        -NoPublish
    if ($LASTEXITCODE -ne 0) {
        throw "The Python environment could not be prepared."
    }
}

& $Python (Join-Path $PSScriptRoot "daily_sync.py")
exit $LASTEXITCODE
