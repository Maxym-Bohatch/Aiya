$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
Set-Location $ProjectRoot

$env:AIYA_ENV_FILE = Join-Path $ProjectRoot ".env.client"

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    throw "PyInstaller is not installed. Install it first: pip install pyinstaller"
}

Get-Process | Where-Object {
    $_.Path -and ([System.IO.Path]::GetFullPath($_.Path) -eq [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot "dist\AiyaClientLauncher.exe")))
} | ForEach-Object {
    Write-Host "[Aiya] Stopping running client launcher before rebuild: $($_.Path)" -ForegroundColor Yellow
    Stop-Process -Id $_.Id -Force
}

& pyinstaller --noconfirm --clean AiyaClientLauncher.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed for AiyaClientLauncher.spec with exit code $LASTEXITCODE"
}

Write-Host "[Aiya] Client EXE build finished: dist\\AiyaClientLauncher.exe" -ForegroundColor Green
