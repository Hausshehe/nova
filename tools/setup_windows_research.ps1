$ErrorActionPreference = 'Stop'

Write-Host 'NOVA - Windows research environment setup'
Write-Host ''

if ($env:OS -ne 'Windows_NT') {
    throw 'This setup script must be run on Windows.'
}

$python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $python = 'py'
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = 'python'
} else {
    throw 'Python is not installed or is not available on PATH. Install Python 3.12.x from python.org first.'
}

Write-Host 'Python launcher:' $python
& $python --version

if (-not (Test-Path '.venv')) {
    Write-Host 'Creating .venv ...'
    & $python -m venv .venv
}

$venvPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment Python was not created: $venvPython"
}

Write-Host 'Upgrading pip ...'
& $venvPython -m pip install --upgrade pip

Write-Host 'Installing Nova Windows dependencies ...'
& $venvPython -m pip install -r requirements-windows.txt

Write-Host ''
Write-Host 'Environment installation complete.'
Write-Host 'This script does NOT connect to MT5 or perform any trading action.'
Write-Host ''
Write-Host 'Next command, after starting the MT5 terminal:'
Write-Host '.\.venv\Scripts\python.exe tools\check_mt5_environment.py'
