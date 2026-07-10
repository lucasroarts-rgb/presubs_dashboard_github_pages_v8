$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path (Join-Path $Root "docs\index.html"))) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "generate_public_site.ps1")
}

if (-not (Test-Path $VenvPython)) {
    throw "Run GERAR_SITE_PUBLICO.bat first."
}

Start-Process powershell.exe -ArgumentList @(
    "-NoProfile",
    "-WindowStyle", "Hidden",
    "-Command", "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8080'"
)

Write-Host "Public preview: http://127.0.0.1:8080" -ForegroundColor Cyan
Write-Host "Press CTRL+C to stop the preview." -ForegroundColor Yellow
& $VenvPython -m http.server 8080 --directory docs
