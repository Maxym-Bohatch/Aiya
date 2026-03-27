$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
Set-Location $ProjectRoot

$env:AIYA_ENV_FILE = Join-Path $ProjectRoot ".env.client"

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    throw "PyInstaller is not installed. Install it first: pip install pyinstaller"
}

pyinstaller --noconfirm --clean AiyaClientLauncher.spec
Write-Host "[Aiya] Client EXE build finished: dist\\AiyaClientLauncher.exe" -ForegroundColor Green
