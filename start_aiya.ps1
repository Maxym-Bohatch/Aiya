$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

. (Join-Path $ProjectRoot "scripts\server\server_common.ps1")

function Start-HostControl([string]$Token) {
    $existing = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -like "*host_control_server.py*"
    } | Select-Object -First 1
    if ($existing) {
        Write-AiyaStep "Host control server is already running."
        return
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        Write-Host "[Aiya] Python is not installed or not in PATH. Skipping host control bridge; Docker services can still start." -ForegroundColor Yellow
        return
    }

    Write-AiyaStep "Starting host control server..."
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $python.Source
    $psi.Arguments = "host_control_server.py"
    $psi.WorkingDirectory = $ProjectRoot
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.Environment["HOST_CONTROL_TOKEN"] = $Token
    $psi.Environment["AIYA_ADMIN_TOKEN"] = Read-AiyaEnvValue -ProjectRoot $ProjectRoot -Name "AIYA_ADMIN_TOKEN"
    [System.Diagnostics.Process]::Start($psi) | Out-Null
    Start-Sleep -Seconds 2
}

Ensure-AiyaEnv -ProjectRoot $ProjectRoot
Ensure-DockerDesktopRunning
$hostToken = Ensure-AiyaHostControlToken -ProjectRoot $ProjectRoot
Start-HostControl -Token $hostToken

$llmMode = Get-AiyaLlmMode -ProjectRoot $ProjectRoot
$composeArgs = Get-AiyaComposeArgs -ProjectRoot $ProjectRoot

Write-AiyaStep "Starting Docker services..."
& docker @composeArgs up -d --build
Sync-AiyaDatabasePassword -ProjectRoot $ProjectRoot -ComposeArgs $composeArgs

Write-AiyaStep "Waiting for API..."
if (-not (Wait-AiyaUrl -Url "http://localhost:8000/health" -Seconds 240)) {
    throw "API did not become ready in time."
}

Write-AiyaStep "Waiting for Aiya web UI..."
if (-not (Wait-AiyaUrl -Url "http://localhost:3000/" -Seconds 120)) {
    throw "Aiya web UI did not become ready in time."
}

$webUiEnabled = $llmMode -ne "external_api"
if ($webUiEnabled) {
    Write-AiyaStep "Waiting for Open WebUI..."
    if (-not (Wait-AiyaUrl -Url "http://localhost:3001/" -Seconds 120)) {
        Write-Host "[Aiya] Open WebUI did not become ready in time, but the core stack is running." -ForegroundColor Yellow
    }
}

Write-AiyaStep "Aiya is ready."
Write-Host ""
Write-Host "Aiya web UI:   http://localhost:3000" -ForegroundColor Cyan
Write-Host "API health:    http://localhost:8000/health" -ForegroundColor Cyan
if ($webUiEnabled) {
    Write-Host "Open WebUI:    http://localhost:3001" -ForegroundColor Cyan
}
Write-Host "Desktop body:  python desktop_companion.py" -ForegroundColor Cyan
