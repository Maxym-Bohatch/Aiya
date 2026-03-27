$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
Set-Location $ProjectRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python is not installed or not available in PATH."
}

$venvDir = Join-Path $ProjectRoot ".venv-client"
if (-not (Test-Path $venvDir)) {
    Write-Host "[Aiya] Creating a dedicated client virtual environment..." -ForegroundColor Cyan
    python -m venv $venvDir
}

$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Client virtual environment looks incomplete: $venvPython"
}

Write-Host "[Aiya] Installing client Python dependencies..." -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

$tesseract = Get-Command tesseract -ErrorAction SilentlyContinue
if (-not $tesseract) {
    $answer = Read-Host "Tesseract was not found. Install it with winget now? (Y/N)"
    if ($answer -match '^(y|yes|т|так)$') {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Start-Process winget -Verb RunAs -ArgumentList 'install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements'
        } else {
            Write-Host "[Aiya] winget is not available. Install Tesseract manually." -ForegroundColor Yellow
        }
    }
}

Write-Host "[Aiya] Client prerequisites are ready. Launch with scripts/client/start_client.ps1 or use the packaged EXE." -ForegroundColor Green
