@echo off
REM Database Schema Reset Script for Windows

echo ==========================================
echo DATABASE SCHEMA RESET
echo ==========================================
echo.
echo WARNING: This will DELETE all trade history!
echo.
set /p confirm="Are you sure you want to continue? (yes/no): "

if not "%confirm%"=="yes" (
    echo Cancelled.
    exit /b 0
)

echo.
echo Resetting database schema...

REM Drop and recreate database
docker exec trading_bot_timescaledb psql -U postgres -c "DROP DATABASE IF EXISTS trading_bot;"
docker exec trading_bot_timescaledb psql -U postgres -c "CREATE DATABASE trading_bot;"

echo OK: Database recreated
echo.
echo Schema will be automatically initialized when bot starts.
echo.
echo Run: python main.py
pause
