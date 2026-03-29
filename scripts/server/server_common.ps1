$ErrorActionPreference = "Stop"

function Get-AiyaProjectRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..\")).Path
}

function Write-AiyaStep([string]$Text) {
    Write-Host "[Aiya] $Text" -ForegroundColor Green
}

function Ensure-AiyaEnv {
    param(
        [string]$ProjectRoot
    )

    Set-Location $ProjectRoot

    if (-not (Test-Path ".env")) {
        if (Test-Path ".env.server") {
            Copy-Item ".env.server" ".env"
        } elseif (Test-Path ".env.server.example") {
            Copy-Item ".env.server.example" ".env"
        } elseif (Test-Path ".env.example") {
            Copy-Item ".env.example" ".env"
        } else {
            throw "No environment template was found. Installer should create .env before server start."
        }
        Write-AiyaStep "Created .env from the server template."
    }
}

function Read-AiyaEnvValue {
    param(
        [string]$ProjectRoot,
        [string]$Name
    )

    $line = Get-Content (Join-Path $ProjectRoot ".env") | Where-Object { $_ -match "^$Name=" } | Select-Object -First 1
    if (-not $line) { return "" }
    return $line.Substring($Name.Length + 1).Trim()
}

function Ensure-AiyaHostControlToken {
    param(
        [string]$ProjectRoot
    )

    $token = Read-AiyaEnvValue -ProjectRoot $ProjectRoot -Name "HOST_CONTROL_TOKEN"
    if (-not $token) {
        $fallback = Read-AiyaEnvValue -ProjectRoot $ProjectRoot -Name "AIYA_ADMIN_TOKEN"
        if (-not $fallback) {
            throw "AIYA_ADMIN_TOKEN is empty in .env. Set it first."
        }
        Add-Content (Join-Path $ProjectRoot ".env") "`nHOST_CONTROL_TOKEN=$fallback"
        Write-AiyaStep "Added HOST_CONTROL_TOKEN to .env using AIYA_ADMIN_TOKEN."
        return $fallback
    }
    return $token
}

function Get-AiyaLlmMode {
    param(
        [string]$ProjectRoot
    )

    $mode = (Read-AiyaEnvValue -ProjectRoot $ProjectRoot -Name "AIYA_LLM_MODE").ToLowerInvariant()
    if ($mode -in @("bundled_ollama", "external_ollama", "external_api")) {
        return $mode
    }
    return "bundled_ollama"
}

function Get-AiyaComposeArgs {
    param(
        [string]$ProjectRoot
    )

    $mode = Get-AiyaLlmMode -ProjectRoot $ProjectRoot
    if ($mode -eq "external_ollama") {
        Write-AiyaStep "Using external Ollama docker compose scenario."
        return @("compose", "-f", "docker-compose.external-ollama.yml")
    }
    if ($mode -eq "external_api") {
        Write-AiyaStep "Using external API docker compose scenario."
        return @("compose", "-f", "docker-compose.external-api.yml")
    }
    Write-AiyaStep "Using bundled Ollama docker compose scenario."
    return @("compose", "-f", "docker-compose.yml")
}

function Find-DockerDesktopExe {
    $candidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe"),
        (Join-Path $env:LocalAppData "Programs\Docker\Docker\Docker Desktop.exe")
    ) | Where-Object { $_ -and (Test-Path $_) }

    return $candidates | Select-Object -First 1
}

function Ensure-DockerDesktopRunning {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI is not installed. Install Docker Desktop first: https://docs.docker.com/desktop/setup/install/windows-install/"
    }

    function Test-DockerEngineReady {
        try {
            $serverVersion = docker version --format "{{.Server.Version}}" 2>$null
            return -not [string]::IsNullOrWhiteSpace($serverVersion)
        } catch {
            return $false
        }
    }

    if (Test-DockerEngineReady) {
        Write-AiyaStep "Docker engine is already available."
        return
    }

    Write-AiyaStep "Docker engine is not ready yet. Trying to start Docker Desktop..."

    $dockerDesktop = Find-DockerDesktopExe
    if (-not $dockerDesktop) {
        throw "Docker Desktop executable was not found. Install Docker Desktop first."
    }

    $running = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
    if (-not $running) {
        Start-Process -FilePath $dockerDesktop | Out-Null
        Write-AiyaStep "Docker Desktop launched."
    } else {
        Write-AiyaStep "Docker Desktop process already exists. Waiting for engine..."
    }

    $deadline = (Get-Date).AddMinutes(4)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerEngineReady) {
            Write-AiyaStep "Docker engine is ready."
            return
        }
        Start-Sleep -Seconds 3
    }

    throw "Docker Desktop did not become ready in time."
}

function Wait-AiyaUrl {
    param(
        [string]$Url,
        [int]$Seconds = 180
    )

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

function Restart-AiyaComposeServices {
    param(
        [string[]]$ComposeArgs,
        [string[]]$Services
    )

    foreach ($service in $Services) {
        try {
            & docker @ComposeArgs restart $service | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-AiyaStep "Restarted docker service: $service"
            }
        } catch {
            Write-Host "[Aiya] Could not restart docker service '$service': $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

function Sync-AiyaDatabasePassword {
    param(
        [string]$ProjectRoot,
        [string[]]$ComposeArgs
    )

    $dbPassword = Read-AiyaEnvValue -ProjectRoot $ProjectRoot -Name "DB_PASSWORD"
    if (-not $dbPassword) {
        Write-Host "[Aiya] DB_PASSWORD is empty in .env, skipping database credential sync." -ForegroundColor Yellow
        return
    }

    $dbContainer = docker ps --format "{{.Names}}" | Where-Object { $_ -eq "aiya_db" } | Select-Object -First 1
    if (-not $dbContainer) {
        Write-AiyaStep "Database container is not running yet, skipping password sync."
        return
    }

    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        & docker exec aiya_db pg_isready -U maxim -d aiya_memory *> $null
        if ($LASTEXITCODE -eq 0) {
            break
        }
        Start-Sleep -Seconds 2
    }

    & docker exec aiya_db pg_isready -U maxim -d aiya_memory *> $null
    if ($LASTEXITCODE -ne 0) {
        $dbExists = (& docker exec aiya_db psql -U maxim -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'aiya_memory'" 2>$null).Trim()
        if ($dbExists -ne "1") {
            Write-AiyaStep "Database aiya_memory is still being initialized, skipping password sync on this run."
            return
        }
        Write-Host "[Aiya] Database is not ready for password sync yet." -ForegroundColor Yellow
        return
    }

    $escapedPassword = $dbPassword.Replace("'", "''")
    $sql = "ALTER USER maxim WITH PASSWORD '$escapedPassword';"
    & docker exec aiya_db psql -U maxim -d aiya_memory -c $sql 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-AiyaStep "Synchronized PostgreSQL password with the current .env configuration."
        Restart-AiyaComposeServices -ComposeArgs $ComposeArgs -Services @("api", "tg_bot")
        return
    }

    Write-Host "[Aiya] Could not synchronize PostgreSQL password automatically." -ForegroundColor Yellow
}
