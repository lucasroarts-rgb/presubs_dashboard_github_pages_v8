$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "Migrate your current v8 project to v9 automation" -ForegroundColor Cyan
Write-Host ""

$defaultPath = "C:\presubs-dashboard\PreSubs_Weekly_Dashboard_v8_Daily_GitHub_Pages\presubs_dashboard_github_pages_v8"
$oldPath = Read-Host "Current v8 folder [$defaultPath]"
if ([string]::IsNullOrWhiteSpace($oldPath)) {
    $oldPath = $defaultPath
}

if (-not (Test-Path $oldPath)) {
    throw "The selected v8 folder does not exist."
}

$dataSource = Join-Path $oldPath "data\presubs.db"
if (Test-Path $dataSource) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Root "data") | Out-Null
    Copy-Item $dataSource (Join-Path $Root "data\presubs.db") -Force
    Write-Host "SQLite database copied." -ForegroundColor Green
}

$credentialsSource = Join-Path $oldPath "data\admin_credentials.txt"
if (Test-Path $credentialsSource) {
    Copy-Item $credentialsSource (Join-Path $Root "data\admin_credentials.txt") -Force
    Write-Host "Local admin credentials copied." -ForegroundColor Green
}

$gitSource = Join-Path $oldPath ".git"
$gitTarget = Join-Path $Root ".git"
if (Test-Path $gitSource) {
    if (Test-Path $gitTarget) {
        Remove-Item $gitTarget -Recurse -Force
    }
    Copy-Item $gitSource $gitTarget -Recurse -Force
    Write-Host "GitHub repository connection copied." -ForegroundColor Green
} else {
    Write-Host "The old folder has no .git directory. Add v9 in GitHub Desktop." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Migration completed." -ForegroundColor Green
Write-Host "Next: run CONFIGURAR_META.bat once."
Write-Host ""
