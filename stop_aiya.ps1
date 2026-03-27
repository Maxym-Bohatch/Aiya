$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "[Aiya] Stopping Docker services..." -ForegroundColor Yellow
docker compose down

$hostControl = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like "*host_control_server.py*"
}
if ($hostControl) {
    $hostControl | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Write-Host "[Aiya] Host control server stopped." -ForegroundColor Yellow
}
