$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
Set-Location $ProjectRoot
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_aiya.ps1
