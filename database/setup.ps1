# Database Setup Script for Windows
# This script sets up TimescaleDB and Redis using Docker

Write-Host "[DATABASE] Trading Bot Database Setup" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is installed
Write-Host "Checking Docker installation..." -ForegroundColor Yellow
try {
    $dockerVersion = docker --version
    Write-Host "[OK] Docker found: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker is not installed!" -ForegroundColor Red
    Write-Host "Please install Docker Desktop from: https://www.docker.com/products/docker-desktop" -ForegroundColor Yellow
    exit 1
}

# Check if Docker is running
Write-Host "Checking if Docker is running..." -ForegroundColor Yellow
try {
    docker ps | Out-Null
    Write-Host "[OK] Docker is running" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker is not running!" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again" -ForegroundColor Yellow
    exit 1
}

# Check if docker-compose is available
Write-Host "Checking docker-compose..." -ForegroundColor Yellow
try {
    $composeVersion = docker-compose --version
    Write-Host "[OK] Docker Compose found: $composeVersion" -ForegroundColor Green
} catch {
        Write-Host "[WARN] docker-compose not found, trying 'docker compose'..." -ForegroundColor Yellow
    try {
        docker compose version | Out-Null
        Write-Host "[OK] Docker Compose (v2) found" -ForegroundColor Green
        $useDockerComposeV2 = $true
    } catch {
        Write-Host "[ERROR] Docker Compose not found!" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "Starting database containers..." -ForegroundColor Yellow

# Navigate to project root
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptPath
Set-Location $projectRoot

# Start containers
if ($useDockerComposeV2) {
    docker compose up -d
} else {
    docker-compose up -d
}

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "[OK] Database containers started successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Waiting for databases to be ready..." -ForegroundColor Yellow
    
    # Wait for TimescaleDB
    $maxWait = 30
    $waited = 0
    while ($waited -lt $maxWait) {
        try {
            $result = docker exec trading_bot_timescaledb pg_isready -U postgres 2>&1
            if ($result -match "accepting connections") {
                Write-Host "[OK] TimescaleDB is ready" -ForegroundColor Green
                break
            }
        } catch {
            # Still waiting
        }
        Start-Sleep -Seconds 2
        $waited += 2
        Write-Host "." -NoNewline -ForegroundColor Gray
    }
    Write-Host ""
    
    # Wait for Redis
    try {
        docker exec trading_bot_redis redis-cli ping | Out-Null
        Write-Host "[OK] Redis is ready" -ForegroundColor Green
    } catch {
        Write-Host "[WARN] Redis might still be starting..." -ForegroundColor Yellow
    }
    
    Write-Host ""
    Write-Host "[INFO] Database Status:" -ForegroundColor Cyan
    Write-Host "  TimescaleDB: localhost:5432" -ForegroundColor White
    Write-Host "  Redis: localhost:6379" -ForegroundColor White
    Write-Host ""
    Write-Host "[TIP] Update your .env file with:" -ForegroundColor Yellow
    Write-Host "  TIMESCALEDB_HOST=localhost" -ForegroundColor Gray
    Write-Host "  TIMESCALEDB_PORT=5432" -ForegroundColor Gray
    Write-Host "  TIMESCALEDB_DATABASE=trading_bot" -ForegroundColor Gray
    Write-Host "  TIMESCALEDB_USER=postgres" -ForegroundColor Gray
    Write-Host "  TIMESCALEDB_PASSWORD=postgres" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  REDIS_HOST=localhost" -ForegroundColor Gray
    Write-Host "  REDIS_PORT=6379" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[OK] Setup complete! You can now run the bot." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[ERROR] Failed to start containers!" -ForegroundColor Red
    Write-Host "Check Docker logs: docker-compose logs" -ForegroundColor Yellow
    exit 1
}
