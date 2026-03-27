$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

powershell -ExecutionPolicy Bypass -File .\scripts\server\start_server.ps1
