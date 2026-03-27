$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
Set-Location $ProjectRoot

if (-not (Test-Path ".env.client")) {
    if (Test-Path ".env.client.example") {
        Copy-Item ".env.client.example" ".env.client"
        Write-Host "[Aiya] Created .env.client from example." -ForegroundColor Green
    }
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python is not installed or not in PATH. Use the packaged AiyaClientLauncher.exe or install Python first."
}

$env:AIYA_ENV_FILE = Join-Path $ProjectRoot ".env.client"

try {
    @'
import importlib
required = ["requests", "PIL", "pytesseract"]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit(",".join(missing))
'@ | python -
} catch {
    Write-Host "[Aiya] Missing Python dependencies for the client launcher." -ForegroundColor Yellow
    $answer = Read-Host "Install client prerequisites now? (Y/N)"
    if ($answer -match '^(y|yes|т|так)$') {
        powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "scripts\client\install_client_prereqs.ps1")
    } else {
        throw "Client prerequisites are missing. Install them and try again."
    }
}

python -m client.launcher
