$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "Migrate your current PreSubs dashboard to v10.4" -ForegroundColor Cyan
Write-Host ""

$currentPath = Read-Host "Path to the current dashboard folder"
if ([string]::IsNullOrWhiteSpace($currentPath) -or -not (Test-Path $currentPath)) {
    throw "The selected folder does not exist."
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "data") | Out-Null

$files = @(
    @{ Source = "data\presubs.db"; Destination = "data\presubs.db"; Label = "SQLite database" },
    @{ Source = "data\admin_credentials.txt"; Destination = "data\admin_credentials.txt"; Label = "admin credentials" },
    @{ Source = "data\dashboard_config.json"; Destination = "data\dashboard_config.json"; Label = "existing settings and annotations" },
    @{ Source = ".env"; Destination = ".env"; Label = "Meta API configuration" }
)

foreach ($item in $files) {
    $source = Join-Path $currentPath $item.Source
    if (Test-Path $source) {
        Copy-Item $source (Join-Path $Root $item.Destination) -Force
        Write-Host "Copied $($item.Label)." -ForegroundColor Green
    }
}

$gitSource = Join-Path $currentPath ".git"
$gitTarget = Join-Path $Root ".git"
if (Test-Path $gitSource) {
    if (Test-Path $gitTarget) { Remove-Item $gitTarget -Recurse -Force }
    Copy-Item $gitSource $gitTarget -Recurse -Force
    Write-Host "GitHub repository connection copied." -ForegroundColor Green
} else {
    Write-Host "No .git folder was found. Add the v10.4 folder in GitHub Desktop." -ForegroundColor Yellow
}

foreach ($folderName in @("exports", "logs")) {
    $source = Join-Path $currentPath $folderName
    if (Test-Path $source) {
        Copy-Item $source (Join-Path $Root $folderName) -Recurse -Force
        Write-Host "Copied $folderName." -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Migration completed." -ForegroundColor Green
Write-Host "Run START_LOCAL_DASHBOARD.bat to review goals and settings."
Write-Host "The historical data does not need another reimport if it already finished successfully in v10."
Write-Host ""
