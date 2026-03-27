$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

function Write-Step([string]$Text) {
    Write-Host "[Aiya] $Text" -ForegroundColor Green
}

function Ensure-Env {
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Step "Created .env from .env.example. Fill in TELEGRAM_TOKEN, DB_PASSWORD, and AIYA_ADMIN_TOKEN if needed."
    }
}

function Read-EnvValue([string]$Name) {
    $line = Get-Content ".env" | Where-Object { $_ -match "^$Name=" } | Select-Object -First 1
    if (-not $line) { return "" }
    return $line.Substring($Name.Length + 1).Trim()
}

function Ensure-HostControlToken {
    $token = Read-EnvValue "HOST_CONTROL_TOKEN"
    if (-not $token) {
        $fallback = Read-EnvValue "AIYA_ADMIN_TOKEN"
        if (-not $fallback) {
            throw "AIYA_ADMIN_TOKEN is empty in .env. Set it first."
        }
        Add-Content ".env" "`nHOST_CONTROL_TOKEN=$fallback"
        $token = $fallback
        Write-Step "Added HOST_CONTROL_TOKEN to .env using AIYA_ADMIN_TOKEN."
    }
    return $token
}

function Start-HostControl([string]$Token) {
    $existing = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -like "*host_control_server.py*"
    } | Select-Object -First 1
    if ($existing) {
        Write-Step "Host control server is already running."
        return
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "Python is not installed or not in PATH. It is needed for host_control_server.py and desktop_companion.py."
    }

    Write-Step "Starting host control server..."
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $python.Source
    $psi.Arguments = "host_control_server.py"
    $psi.WorkingDirectory = $ProjectRoot
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.Environment["HOST_CONTROL_TOKEN"] = $Token
    $psi.Environment["AIYA_ADMIN_TOKEN"] = Read-EnvValue "AIYA_ADMIN_TOKEN"
    [System.Diagnostics.Process]::Start($psi) | Out-Null
    Start-Sleep -Seconds 2
}

function Wait-Url([string]$Url, [int]$Seconds = 180) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 8 | Out-Null
            return $true
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

Ensure-Env
$hostToken = Ensure-HostControlToken
Start-HostControl -Token $hostToken

Write-Step "Starting Docker services..."
docker compose up -d --build

Write-Step "Waiting for API..."
if (-not (Wait-Url "http://localhost:8000/health" 240)) {
    throw "API did not become ready in time."
}

Write-Step "Waiting for Aiya web UI..."
if (-not (Wait-Url "http://localhost:3000/" 120)) {
    throw "Aiya web UI did not become ready in time."
}

Write-Step "Aiya is ready."
Write-Host ""
Write-Host "Aiya web UI:   http://localhost:3000" -ForegroundColor Cyan
Write-Host "API health:    http://localhost:8000/health" -ForegroundColor Cyan
Write-Host "Open WebUI:    http://localhost:3001" -ForegroundColor Cyan
Write-Host "Desktop body:  python desktop_companion.py" -ForegroundColor Cyan
