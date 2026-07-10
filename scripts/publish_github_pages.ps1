$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "generate_public_site.ps1")
if ($LASTEXITCODE -ne 0) { throw "The public files were not generated." }

$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git -or -not (Test-Path (Join-Path $Root ".git"))) {
    Write-Host "This folder is not connected to GitHub yet." -ForegroundColor Yellow
    Write-Host "Open GitHub Desktop, add this folder, and publish the repository." -ForegroundColor White
    Start-Process explorer.exe $Root
    exit 0
}

& git add docs .gitignore README.md
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

& git push
if ($LASTEXITCODE -ne 0) {
    Write-Host "The files were generated and committed, but Git could not push them." -ForegroundColor Yellow
    Write-Host "Open GitHub Desktop and click Push origin." -ForegroundColor White
    exit 0
}

Write-Host ""
Write-Host "Dashboard sent to GitHub successfully." -ForegroundColor Green
Write-Host "GitHub Pages will update after the new commit is processed." -ForegroundColor White
