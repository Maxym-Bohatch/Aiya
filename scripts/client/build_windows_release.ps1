$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

function Stop-LockingAiyaProcesses {
    $distDir = Join-Path $ProjectRoot "dist"
    $targets = @(
        (Join-Path $distDir "AiyaClientLauncher.exe"),
        (Join-Path $distDir "AiyaServerLauncher.exe"),
        (Join-Path $distDir "AiyaUninstaller.exe"),
        (Join-Path $distDir "AiyaInstaller.exe")
    ) | ForEach-Object { [System.IO.Path]::GetFullPath($_) }

    Get-Process | Where-Object {
        $_.Path -and ([System.IO.Path]::GetFullPath($_.Path) -in $targets)
    } | ForEach-Object {
        Write-Host "[Aiya] Stopping running build target: $($_.Path)" -ForegroundColor Yellow
        Stop-Process -Id $_.Id -Force
    }
}

function Invoke-PyInstallerBuild {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SpecFile
    )

    & pyinstaller --noconfirm --clean $SpecFile
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed for $SpecFile with exit code $LASTEXITCODE"
    }
}

Stop-LockingAiyaProcesses

Invoke-PyInstallerBuild "AiyaClientLauncher.spec"
Invoke-PyInstallerBuild "AiyaServerLauncher.spec"
Invoke-PyInstallerBuild "AiyaUninstaller.spec"
Invoke-PyInstallerBuild "AiyaInstaller.spec"

$releaseDir = Join-Path $ProjectRoot "release\windows"
New-Item -ItemType Directory -Force $releaseDir | Out-Null
Copy-Item "dist\AiyaClientLauncher.exe" (Join-Path $releaseDir "AiyaClientLauncher.exe") -Force
Copy-Item "dist\AiyaServerLauncher.exe" (Join-Path $releaseDir "AiyaServerLauncher.exe") -Force
Copy-Item "dist\AiyaInstaller.exe" (Join-Path $releaseDir "AiyaInstaller.exe") -Force
Copy-Item "dist\AiyaUninstaller.exe" (Join-Path $releaseDir "AiyaUninstaller.exe") -Force
Copy-Item ".env.client.example" (Join-Path $releaseDir ".env.client.example") -Force
Copy-Item "docs\CLIENT_SETUP.md" (Join-Path $releaseDir "CLIENT_SETUP.md") -Force
Copy-Item "docs\DOCKER_MIGRATION.md" (Join-Path $releaseDir "DOCKER_MIGRATION.md") -Force
Copy-Item "docs\INSTALLER.md" (Join-Path $releaseDir "INSTALLER.md") -Force

Write-Host "[Aiya] Windows release package is ready in release/windows" -ForegroundColor Green
