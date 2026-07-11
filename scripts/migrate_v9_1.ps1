$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "Migrate v9.1 history project to v9.2 date analysis" -ForegroundColor Cyan
Write-Host ""

$defaultPath = "C:\presubs-dashboard\PreSubs_Weekly_Dashboard_v9_1_Historical_2026\presubs_dashboard_github_pages_v9_1_history"
$oldPath = Read-Host "Current v9.1 folder [$defaultPath]"
if ([string]::IsNullOrWhiteSpace($oldPath)) { $oldPath = $defaultPath }
if (-not (Test-Path $oldPath)) { throw "The selected v9.1 folder does not exist." }

foreach ($relative in @("data", "exports", "logs")) {
    $source = Join-Path $oldPath $relative
    $destination = Join-Path $Root $relative
    if (Test-Path $source) {
        New-Item -ItemType Directory -Force -Path $destination | Out-Null
        Copy-Item (Join-Path $source "*") $destination -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "$relative copied." -ForegroundColor Green
    }
}

foreach ($file in @(".env", "history_progress.json")) {
    $source = Join-Path $oldPath $file
    if (Test-Path $source) { Copy-Item $source (Join-Path $Root $file) -Force; Write-Host "$file copied." -ForegroundColor Green }
}

$gitSource = Join-Path $oldPath ".git"
$gitTarget = Join-Path $Root ".git"
if (Test-Path $gitSource) {
    if (Test-Path $gitTarget) { Remove-Item $gitTarget -Recurse -Force }
    Copy-Item $gitSource $gitTarget -Recurse -Force
    Write-Host "GitHub connection copied." -ForegroundColor Green
} else {
    Write-Host "No .git folder was found. Add this v9.2 folder in GitHub Desktop." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Migration completed." -ForegroundColor Green
Write-Host "Run GERAR_SITE_PUBLICO.bat and then PUBLICAR_NO_GITHUB.bat."
Write-Host ""
