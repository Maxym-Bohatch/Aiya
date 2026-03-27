$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

pyinstaller --noconfirm --clean AiyaClientLauncher.spec
pyinstaller --noconfirm --clean AiyaUninstaller.spec
pyinstaller --noconfirm --clean AiyaInstaller.spec

$releaseDir = Join-Path $ProjectRoot "release\windows"
New-Item -ItemType Directory -Force $releaseDir | Out-Null
Copy-Item "dist\AiyaClientLauncher.exe" (Join-Path $releaseDir "AiyaClientLauncher.exe") -Force
Copy-Item "dist\AiyaInstaller.exe" (Join-Path $releaseDir "AiyaInstaller.exe") -Force
Copy-Item "dist\AiyaUninstaller.exe" (Join-Path $releaseDir "AiyaUninstaller.exe") -Force
Copy-Item ".env.client.example" (Join-Path $releaseDir ".env.client.example") -Force
Copy-Item "docs\CLIENT_SETUP.md" (Join-Path $releaseDir "CLIENT_SETUP.md") -Force
Copy-Item "docs\DOCKER_MIGRATION.md" (Join-Path $releaseDir "DOCKER_MIGRATION.md") -Force
Copy-Item "docs\INSTALLER.md" (Join-Path $releaseDir "INSTALLER.md") -Force

Write-Host "[Aiya] Windows release package is ready in release/windows" -ForegroundColor Green
