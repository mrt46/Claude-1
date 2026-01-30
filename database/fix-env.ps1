# Fix .env file for Docker Compose compatibility
# This script wraps comma-separated values in quotes

$envFile = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..\.env"

if (-not (Test-Path $envFile)) {
    Write-Host "[ERROR] .env file not found at: $envFile" -ForegroundColor Red
    exit 1
}

Write-Host "Fixing .env file for Docker Compose compatibility..." -ForegroundColor Yellow

# Read the file
$content = Get-Content $envFile -Raw -Encoding UTF8

# Pattern to match: VARIABLE=value1,value2,value3 (without quotes)
# This regex finds lines with comma-separated values that aren't already quoted
$pattern = '(?m)^(\s*TRADING_SYMBOLS\s*=\s*)([^"''\r\n][^,\r\n]*(?:,[^,\r\n]+)+)(\s*)$'

if ($content -match $pattern) {
    # Replace with quoted version
    $content = $content -replace $pattern, '$1"$2"$3'
    
    # Write back
    [System.IO.File]::WriteAllText($envFile, $content, [System.Text.Encoding]::UTF8)
    
    Write-Host "[OK] Fixed TRADING_SYMBOLS line - values are now quoted" -ForegroundColor Green
    Write-Host ""
    Write-Host "The line should now look like:" -ForegroundColor Cyan
    Write-Host '  TRADING_SYMBOLS="SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT"' -ForegroundColor Gray
} else {
    Write-Host "[INFO] No unquoted comma-separated values found, or already fixed" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "You can now run: .\database\setup.ps1" -ForegroundColor Green
