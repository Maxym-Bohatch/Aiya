$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
Set-Location $ProjectRoot

if (-not (Test-Path ".env.client")) {
    if (Test-Path ".env.client.example") {
        Copy-Item ".env.client.example" ".env.client"
        Write-Host "[Aiya] Created .env.client from example." -ForegroundColor Green
    }
}

$env:AIYA_ENV_FILE = Join-Path $ProjectRoot ".env.client"
python -m client.launcher
