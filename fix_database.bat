@echo off
REM Database troubleshooting and fix script for Windows

echo ==========================================
echo DATABASE TROUBLESHOOTING HELPER
echo ==========================================
echo.

REM Check if Docker is running
docker ps >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not running!
    echo        Please start Docker Desktop and try again
    pause
    exit /b 1
)

echo OK: Docker is running
echo.

REM Check for TimescaleDB container
echo Checking for TimescaleDB container...
docker ps | findstr /C:"timescaledb" >nul 2>&1
if not errorlevel 1 (
    echo OK: TimescaleDB container is running
    set CONTAINER_NAME=timescaledb
    goto :test_connection
)

docker ps -a | findstr /C:"timescaledb" >nul 2>&1
if not errorlevel 1 (
    echo WARNING: TimescaleDB container exists but is not running
    echo          Starting container...
    docker start timescaledb
    timeout /t 3 /nobreak >nul
    set CONTAINER_NAME=timescaledb
    goto :test_connection
)

echo ERROR: No TimescaleDB container found!
echo.
echo Creating new TimescaleDB container...
docker run -d --name timescaledb -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=trading_bot timescale/timescaledb:latest-pg14

echo Waiting 5 seconds for database to initialize...
timeout /t 5 /nobreak >nul
set CONTAINER_NAME=timescaledb

:test_connection
echo.
echo ==========================================
echo DATABASE CONNECTION TEST
echo ==========================================

REM Test connection
echo Testing connection...
docker exec %CONTAINER_NAME% psql -U postgres -d trading_bot -c "SELECT 1;" >nul 2>&1
if not errorlevel 1 (
    echo OK: Database connection successful!
) else (
    echo WARNING: Connection failed
    docker exec %CONTAINER_NAME% psql -U postgres -d trading_bot -c "SELECT 1;"
)

echo.
echo ==========================================
echo DATABASE PASSWORD INFO
echo ==========================================
echo.

echo Current .env configuration:
if exist ".env" (
    findstr "TIMESCALEDB" .env
) else (
    echo ERROR: .env file not found!
    echo        Run: python debug_bot.py ^(it will create a template^)
)

echo.
echo ==========================================
echo OPTIONS
echo ==========================================
echo.
echo Choose an option:
echo   1^) Test current password from .env
echo   2^) Reset password to 'postgres'
echo   3^) Set custom password
echo   4^) View database logs
echo   5^) Restart database container
echo   6^) Remove and recreate container ^(DANGER: deletes all data!^)
echo   q^) Quit
echo.
set /p choice="Enter choice: "

if "%choice%"=="1" goto test_password
if "%choice%"=="2" goto reset_password
if "%choice%"=="3" goto custom_password
if "%choice%"=="4" goto view_logs
if "%choice%"=="5" goto restart_container
if "%choice%"=="6" goto recreate_container
if "%choice%"=="q" goto quit
echo Invalid choice
goto end

:test_password
echo.
echo Testing connection with .env password...
echo This feature requires manual testing
echo.
echo Run this command:
echo   docker exec -it timescaledb psql -U postgres -d trading_bot
echo.
echo If it asks for a password, use the password from your .env file
goto end

:reset_password
echo.
echo Resetting password to 'postgres'...
docker exec %CONTAINER_NAME% psql -U postgres -c "ALTER USER postgres PASSWORD 'postgres';"
echo OK: Password reset to 'postgres'
echo.
echo Update your .env file:
echo   TIMESCALEDB_PASSWORD=postgres
goto end

:custom_password
echo.
set /p newpass="Enter new password: "
docker exec %CONTAINER_NAME% psql -U postgres -c "ALTER USER postgres PASSWORD '%newpass%';"
echo OK: Password updated to '%newpass%'
echo.
echo Update your .env file:
echo   TIMESCALEDB_PASSWORD=%newpass%
goto end

:view_logs
echo.
echo Last 50 lines of database logs:
echo ==========================================
docker logs --tail 50 %CONTAINER_NAME%
goto end

:restart_container
echo.
echo Restarting database container...
docker restart %CONTAINER_NAME%
timeout /t 3 /nobreak >nul
echo OK: Container restarted
goto end

:recreate_container
echo.
set /p confirm="WARNING: This will DELETE ALL DATA! Are you sure? (yes/no): "
if not "%confirm%"=="yes" (
    echo Cancelled
    goto end
)
echo Removing container...
docker stop %CONTAINER_NAME%
docker rm %CONTAINER_NAME%
echo Creating new container with password 'postgres'...
docker run -d --name timescaledb -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=trading_bot timescale/timescaledb:latest-pg14
timeout /t 5 /nobreak >nul
echo OK: New container created with password 'postgres'
echo    Update your .env file: TIMESCALEDB_PASSWORD=postgres
goto end

:quit
echo Goodbye!
exit /b 0

:end
echo.
echo ==========================================
echo NEXT STEPS
echo ==========================================
echo.
echo 1. Make sure your .env file has the correct password
echo 2. Run: python debug_bot.py
echo 3. If all tests pass, run: python main.py
echo.
pause
