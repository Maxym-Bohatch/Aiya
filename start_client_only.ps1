$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

powershell -ExecutionPolicy Bypass -File .\scripts\client\start_client.ps1
