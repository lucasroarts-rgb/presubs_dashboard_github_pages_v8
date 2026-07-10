$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$DataDir = Join-Path $Root "data"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$CredentialsFile = Join-Path $DataDir "admin_credentials.txt"

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

function Find-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return @{ Command = $py.Source; Arguments = @("-3") } }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @{ Command = $python.Source; Arguments = @() } }

    throw 'Python was not found. Install Python 3.11 or newer and select "Add Python to PATH".'
}

function Invoke-NativeProcess {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @()
    )

    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $Arguments `
        -WorkingDirectory $Root `
        -Wait `
        -PassThru `
        -NoNewWindow

    return $process.ExitCode
}

function Read-Credentials {
    $values = @{}
    Get-Content $CredentialsFile | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') {
            $values[$matches[1].Trim()] = $matches[2].Trim()
        }
    }
    return $values
}

function New-AdminCredentials {
    $bytes = New-Object byte[] 18
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()

    $password = [Convert]::ToBase64String($bytes)
    $password = $password.Replace("+", "A").Replace("/", "B").Replace("=", "")

    @(
        "ADMIN_USER=lucas"
        "ADMIN_PASSWORD=$password"
    ) | Set-Content -Path $CredentialsFile -Encoding ASCII
}

$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $existing = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    if ($existing -and $existing.ProcessName -match 'python|pythonw|uvicorn') {
        Stop-Process -Id $existing.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    } else {
        throw "Port 8000 is already being used by another application."
    }
}

$pythonLauncher = Find-Python

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating the local Python environment..." -ForegroundColor Cyan
    $arguments = @()
    $arguments += $pythonLauncher.Arguments
    $arguments += @("-m", "venv", ".venv")
    $exitCode = Invoke-NativeProcess -FilePath $pythonLauncher.Command -Arguments $arguments
    if ($exitCode -ne 0 -or -not (Test-Path $VenvPython)) {
        throw "The Python environment could not be created."
    }
}

$dependencyExitCode = Invoke-NativeProcess -FilePath $VenvPython -Arguments @("scripts\check_dependencies.py")
if ($dependencyExitCode -ne 0) {
    Write-Host "Installing the required packages..." -ForegroundColor Cyan
    $pipExitCode = Invoke-NativeProcess -FilePath $VenvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip")
    if ($pipExitCode -ne 0) { throw "pip could not be updated." }

    $requirementsExitCode = Invoke-NativeProcess -FilePath $VenvPython -Arguments @("-m", "pip", "install", "-r", "requirements.txt")
    if ($requirementsExitCode -ne 0) { throw "The required packages could not be installed." }
}

if (-not (Test-Path $CredentialsFile)) { New-AdminCredentials }
$credentials = Read-Credentials
$env:ADMIN_USER = $credentials["ADMIN_USER"]
$env:ADMIN_PASSWORD = $credentials["ADMIN_PASSWORD"]

Write-Host ""
Write-Host "Starting the local PreSubs dashboard..." -ForegroundColor Cyan
Write-Host "Dashboard: http://127.0.0.1:8000" -ForegroundColor White
Write-Host "Admin:     http://127.0.0.1:8000/admin" -ForegroundColor White
Write-Host "User:      $($credentials['ADMIN_USER'])" -ForegroundColor White
Write-Host "Password:  $($credentials['ADMIN_PASSWORD'])" -ForegroundColor White
Write-Host ""
Write-Host "Keep this window open. Press CTRL+C to stop." -ForegroundColor Yellow
Write-Host ""

Start-Process powershell.exe -ArgumentList @(
    "-NoProfile",
    "-WindowStyle", "Hidden",
    "-Command", "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8000'"
)

& $VenvPython -m uvicorn app:app --host 127.0.0.1 --port 8000
