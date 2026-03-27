$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
Set-Location $ProjectRoot

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.server") {
        Copy-Item ".env.server" ".env"
    } elseif (Test-Path ".env.server.example") {
        Copy-Item ".env.server.example" ".env"
    } else {
        Copy-Item ".env.example" ".env"
    }
}

docker compose down
docker compose up -d --build
Write-Host "[Aiya] Docker rebuild finished." -ForegroundColor Green
