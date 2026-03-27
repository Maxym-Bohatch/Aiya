$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
Set-Location $ProjectRoot

$distDir = Join-Path $ProjectRoot "dist"
$releaseDir = Join-Path $ProjectRoot "release\client_bundle"
$exePath = Join-Path $distDir "AiyaClientLauncher.exe"

if (-not (Test-Path $exePath)) {
    throw "Client EXE not found. Build it first with scripts/client/build_client_exe.ps1"
}

New-Item -ItemType Directory -Force $releaseDir | Out-Null
Copy-Item $exePath (Join-Path $releaseDir "AiyaClientLauncher.exe") -Force
Copy-Item ".env.client.example" (Join-Path $releaseDir ".env.client.example") -Force
Copy-Item "docs\CLIENT_SETUP.md" (Join-Path $releaseDir "CLIENT_SETUP.md") -Force
Copy-Item "docs\DOCKER_MIGRATION.md" (Join-Path $releaseDir "DOCKER_MIGRATION.md") -Force

Write-Host "[Aiya] Client bundle is ready in release/client_bundle" -ForegroundColor Green
