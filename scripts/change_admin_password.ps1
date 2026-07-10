$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$DataDir = Join-Path $Root "data"
$CredentialsFile = Join-Path $DataDir "admin_credentials.txt"

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

Write-Host ""
Write-Host "Change PreSubs admin credentials" -ForegroundColor Cyan
Write-Host ""

$user = Read-Host "Admin user"
if ([string]::IsNullOrWhiteSpace($user)) {
    $user = "lucas"
}

$securePassword = Read-Host "New password (minimum 12 characters)" -AsSecureString
$password = [System.Net.NetworkCredential]::new("", $securePassword).Password

if ($password.Length -lt 12) {
    throw "The password must contain at least 12 characters."
}

@(
    "ADMIN_USER=$user"
    "ADMIN_PASSWORD=$password"
) | Set-Content -Path $CredentialsFile -Encoding ASCII

Write-Host ""
Write-Host "Credentials saved." -ForegroundColor Green
Write-Host "Restart the dashboard for the change to take effect."
Write-Host ""
