$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

function Find-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return @{ Command = $py.Source; Arguments = @("-3") } }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @{ Command = $python.Source; Arguments = @() } }

    throw 'Python was not found. Install Python 3.11 or newer and select "Add Python to PATH".'
}

function Invoke-NativeProcess {
    param([string]$FilePath, [string[]]$Arguments = @())
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $Root -Wait -PassThru -NoNewWindow
    return $process.ExitCode
}

$launcher = Find-Python

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating the local Python environment..." -ForegroundColor Cyan
    $arguments = @()
    $arguments += $launcher.Arguments
    $arguments += @("-m", "venv", ".venv")
    $exitCode = Invoke-NativeProcess -FilePath $launcher.Command -Arguments $arguments
    if ($exitCode -ne 0) { throw "The Python environment could not be created." }
}

$dependencyExitCode = Invoke-NativeProcess -FilePath $VenvPython -Arguments @("scripts\check_dependencies.py")
if ($dependencyExitCode -ne 0) {
    Write-Host "Installing the required packages..." -ForegroundColor Cyan
    $exitCode = Invoke-NativeProcess -FilePath $VenvPython -Arguments @("-m", "pip", "install", "-r", "requirements.txt")
    if ($exitCode -ne 0) { throw "The required packages could not be installed." }
}

Write-Host ""
Write-Host "Generating the public GitHub Pages site..." -ForegroundColor Cyan
$exitCode = Invoke-NativeProcess -FilePath $VenvPython -Arguments @("scripts\generate_public_site.py")
if ($exitCode -ne 0) { throw "The public site could not be generated." }

Write-Host ""
Write-Host "Done. The public files are in the docs folder." -ForegroundColor Green
Write-Host ""
