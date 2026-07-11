param(
    [int]$Year = 0,
    [string]$Start = "",
    [string]$End = "",
    [switch]$Force,
    [switch]$NoPublish
)

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

    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $Arguments `
        -WorkingDirectory $Root `
        -Wait `
        -PassThru `
        -NoNewWindow

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

$dependencyExitCode = Invoke-NativeProcess `
    -FilePath $VenvPython `
    -Arguments @("scripts\check_dependencies.py")

if ($dependencyExitCode -ne 0) {
    Write-Host "Installing or updating the required packages..." -ForegroundColor Cyan
    $exitCode = Invoke-NativeProcess `
        -FilePath $VenvPython `
        -Arguments @("-m", "pip", "install", "-r", "requirements.txt")
    if ($exitCode -ne 0) { throw "The required packages could not be installed." }
}

$arguments = @("scripts\backfill_meta.py")
if ($Year -gt 0) {
    $arguments += @("--year", [string]$Year)
} elseif ($Start) {
    $arguments += @("--start", $Start)
    if ($End) {
        $arguments += @("--end", $End)
    }
}
if ($Force) { $arguments += "--force" }
if ($NoPublish) { $arguments += "--no-publish" } else { $arguments += "--publish" }

$exitCode = Invoke-NativeProcess -FilePath $VenvPython -Arguments $arguments
if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "Historical import stopped with an error." -ForegroundColor Red
    exit $exitCode
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
