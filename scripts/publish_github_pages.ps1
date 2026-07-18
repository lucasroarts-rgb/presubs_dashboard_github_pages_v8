$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$git = Get-Command git -ErrorAction SilentlyContinue
$hasRepository = $git -and (Test-Path (Join-Path $Root ".git"))

if ($hasRepository) {
    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -eq "HEAD") {
        throw "Git is in detached HEAD mode. Finish or abort the previous rebase before publishing."
    }

    Write-Host "Synchronizing with GitHub before generating the dashboard..." -ForegroundColor Cyan
    & git fetch origin
    if ($LASTEXITCODE -ne 0) { throw "Git could not fetch the remote repository." }

    & git pull --rebase --autostash origin $branch
    if ($LASTEXITCODE -ne 0) {
        throw "Git could not complete Pull origin. Resolve the conflict before publishing."
    }
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "generate_public_site.ps1")
if ($LASTEXITCODE -ne 0) { throw "The public files were not generated." }

if (-not $hasRepository) {
    Write-Host "This folder is not connected to GitHub yet." -ForegroundColor Yellow
    Write-Host "Open GitHub Desktop, add this folder, and publish the repository." -ForegroundColor White
    Start-Process explorer.exe $Root
    exit 0
}

& git add -A
& git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "There are no new public changes to publish." -ForegroundColor Yellow
    exit 0
}

$message = "Update dashboard " + (Get-Date -Format "yyyy-MM-dd HH:mm")
& git commit -m $message
if ($LASTEXITCODE -ne 0) {
    throw "Git could not create the update commit. Open GitHub Desktop to review it."
}

& git push origin $branch
if ($LASTEXITCODE -ne 0) {
    Write-Host "The files were generated and committed, but Git could not push them." -ForegroundColor Yellow
    Write-Host "Open GitHub Desktop and click Push origin." -ForegroundColor White
    exit 0
}

Write-Host ""
Write-Host "Dashboard sent to GitHub successfully." -ForegroundColor Green
Write-Host "GitHub Pages will update after the new commit is processed." -ForegroundColor White
