$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
Set-Location $ProjectRoot
powershell -ExecutionPolicy Bypass -File .\start_aiya.ps1
