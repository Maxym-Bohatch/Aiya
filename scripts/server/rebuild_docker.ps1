$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
Set-Location $ProjectRoot

. (Join-Path $ProjectRoot "scripts\server\server_common.ps1")

Ensure-AiyaEnv -ProjectRoot $ProjectRoot
Ensure-DockerDesktopRunning
$composeArgs = Get-AiyaComposeArgs -ProjectRoot $ProjectRoot

& docker @composeArgs down
& docker @composeArgs up -d --build
Sync-AiyaDatabasePassword -ProjectRoot $ProjectRoot -ComposeArgs $composeArgs

Write-AiyaStep "Docker rebuild finished."
