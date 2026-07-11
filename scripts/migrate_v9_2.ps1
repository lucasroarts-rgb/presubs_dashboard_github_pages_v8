$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "Migrate v9.2 to v9.3 quiz exclusion" -ForegroundColor Cyan
Write-Host ""

$defaultPath = "C:\presubs-dashboard\PreSubs_Weekly_Dashboard_v9_2_Date_Analysis\presubs_dashboard_github_pages_v9_2_date_analysis"
$oldPath = Read-Host "Current v9.2 or v9.1 folder [$defaultPath]"
if ([string]::IsNullOrWhiteSpace($oldPath)) { $oldPath = $defaultPath }
if (-not (Test-Path $oldPath)) { throw "The selected project folder does not exist." }

foreach ($relative in @("data", "exports", "logs", "backups")) {
    $source = Join-Path $oldPath $relative
    $destination = Join-Path $Root $relative
    if (Test-Path $source) {
        New-Item -ItemType Directory -Force -Path $destination | Out-Null
        Copy-Item (Join-Path $source "*") $destination -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "$relative copied." -ForegroundColor Green
    }
}

$envSource = Join-Path $oldPath ".env"
$envTarget = Join-Path $Root ".env"
if (Test-Path $envSource) {
    Copy-Item $envSource $envTarget -Force
    $content = Get-Content $envTarget -Raw
    if ($content -notmatch "META_EXCLUDE_NAME_TERMS=") {
        Add-Content $envTarget "META_EXCLUDE_NAME_TERMS=QUIZ,QUIZ REGISTRATION,QUIZ REGISTRATIONS"
    }
    $content = Get-Content $envTarget -Raw
    $content = [regex]::Replace($content, "(?m)^META_RESULT_ACTION_TYPE=.*$", "META_RESULT_ACTION_TYPE=offsite_conversion.fb_pixel_complete_registration")
    Set-Content $envTarget $content -Encoding UTF8
    Write-Host ".env copied and corrected." -ForegroundColor Green
}

$gitSource = Join-Path $oldPath ".git"
$gitTarget = Join-Path $Root ".git"
if (Test-Path $gitSource) {
    if (Test-Path $gitTarget) { Remove-Item $gitTarget -Recurse -Force }
    Copy-Item $gitSource $gitTarget -Recurse -Force
    Write-Host "GitHub connection copied." -ForegroundColor Green
}

Write-Host ""
Write-Host "Migration completed." -ForegroundColor Green
Write-Host "IMPORTANT: run REIMPORTAR_HISTORICO_2026.bat to overwrite weeks that included Quiz spend." -ForegroundColor Yellow
Write-Host ""
