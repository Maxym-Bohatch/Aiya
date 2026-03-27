$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

Write-Host "[Aiya] Checking server prerequisites..." -ForegroundColor Green

if (Test-Command "nvidia-smi") {
    Write-Host "[Aiya] NVIDIA GPU detected:" -ForegroundColor Green
    nvidia-smi
    Write-Host "[Aiya] Docker Desktop on Windows can use NVIDIA GPU through WSL if the driver is current." -ForegroundColor Yellow
} else {
    Write-Host "[Aiya] nvidia-smi not found. Server will still work in CPU mode." -ForegroundColor Yellow
}

if (-not (Test-Command "wsl")) {
    Write-Host "WSL command not found. Windows may require WSL installation or update." -ForegroundColor Yellow
} else {
    try { wsl --status } catch { Write-Host "WSL status check failed: $($_.Exception.Message)" -ForegroundColor Yellow }
}

if (-not (Test-Command "winget")) {
    Write-Host "winget not found. Install Docker Desktop manually from https://docs.docker.com/desktop/setup/install/windows-install/" -ForegroundColor Yellow
    exit 1
}

Write-Host "[Aiya] Installing Docker Desktop via winget..." -ForegroundColor Green
winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements

Write-Host "[Aiya] Docker Desktop install command finished." -ForegroundColor Green
Write-Host "If Docker asks for WSL updates, GPU support, or a reboot, complete those steps before running start_server_only.ps1" -ForegroundColor Yellow
