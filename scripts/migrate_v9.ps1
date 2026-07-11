$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "Migrate your configured v9 project to v9.1" -ForegroundColor Cyan
Write-Host ""

$defaultPath = "C:\presubs-dashboard\PreSubs_Weekly_Dashboard_v9_Meta_Automation\presubs_dashboard_github_pages_v9_automation"
$oldPath = Read-Host "Current v9 folder [$defaultPath]"
if ([string]::IsNullOrWhiteSpace($oldPath)) {
    $oldPath = $defaultPath
}

if (-not (Test-Path $oldPath)) {
    throw "The selected v9 folder does not exist."
}

$items = @(
    @{ Relative = ".env"; Type = "File" },
    @{ Relative = "data\presubs.db"; Type = "File" },
    @{ Relative = "data\admin_credentials.txt"; Type = "File" },
    @{ Relative = ".git"; Type = "Directory" },
    @{ Relative = "exports"; Type = "Directory" },
    @{ Relative = "logs"; Type = "Directory" }
)

foreach ($item in $items) {
    $source = Join-Path $oldPath $item.Relative
    $destination = Join-Path $Root $item.Relative

    if (-not (Test-Path $source)) {
        continue
    }

    $parent = Split-Path -Parent $destination
    if ($parent) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }

    if ($item.Type -eq "Directory") {
        if (Test-Path $destination) {
            Remove-Item $destination -Recurse -Force
        }
        Copy-Item $source $destination -Recurse -Force
    } else {
        Copy-Item $source $destination -Force
    }

    Write-Host "Copied: $($item.Relative)" -ForegroundColor Green
}

Write-Host ""
Write-Host "Migration completed." -ForegroundColor Green
Write-Host "Next: run IMPORTAR_HISTORICO_2026.bat."
Write-Host ""
