#!/bin/bash
# Database troubleshooting and fix script

echo "=========================================="
echo "DATABASE TROUBLESHOOTING HELPER"
echo "=========================================="
echo ""

# Check if Docker is running
if ! docker ps &> /dev/null; then
    echo "❌ Docker is not running!"
    echo "   Please start Docker Desktop and try again"
    exit 1
fi

echo "✅ Docker is running"
echo ""

# Check for TimescaleDB container
echo "Checking for TimescaleDB container..."
if docker ps | grep -q timescaledb; then
    echo "✅ TimescaleDB container is running"
    CONTAINER_NAME="timescaledb"
elif docker ps -a | grep -q timescaledb; then
    echo "⚠️  TimescaleDB container exists but is not running"
    echo "   Starting container..."
    docker start timescaledb
    sleep 3
    CONTAINER_NAME="timescaledb"
else
    echo "❌ No TimescaleDB container found!"
    echo ""
    echo "Creating new TimescaleDB container..."
    docker run -d \
        --name timescaledb \
        -p 5432:5432 \
        -e POSTGRES_PASSWORD=postgres \
        -e POSTGRES_DB=trading_bot \
        timescale/timescaledb:latest-pg14

    echo "⏳ Waiting 5 seconds for database to initialize..."
    sleep 5
    CONTAINER_NAME="timescaledb"
fi

echo ""
echo "=========================================="
echo "DATABASE CONNECTION TEST"
echo "=========================================="

# Test connection
echo "Testing connection..."
if docker exec $CONTAINER_NAME psql -U postgres -d trading_bot -c "SELECT 1;" &> /dev/null; then
    echo "✅ Database connection successful!"
else
    echo "⚠️  Connection failed, checking status..."
    docker exec $CONTAINER_NAME psql -U postgres -d trading_bot -c "SELECT 1;"
fi

echo ""
echo "=========================================="
echo "DATABASE PASSWORD INFO"
echo "=========================================="

echo ""
echo "Current .env configuration:"
if [ -f ".env" ]; then
    grep "TIMESCALEDB" .env | sed 's/PASSWORD=.*/PASSWORD=******/'
else
    echo "❌ .env file not found!"
    echo "   Run: python debug_bot.py (it will create a template)"
fi

echo ""
echo "=========================================="
echo "OPTIONS"
echo "=========================================="
echo ""
echo "Choose an option:"
echo "  1) Test current password from .env"
echo "  2) Reset password to 'postgres'"
echo "  3) Set custom password"
echo "  4) View database logs"
echo "  5) Restart database container"
echo "  6) Remove and recreate container (DANGER: deletes all data!)"
echo "  q) Quit"
echo ""
read -p "Enter choice: " choice

case $choice in
    1)
        echo ""
        echo "Testing connection with .env password..."
        # Load password from .env
        if [ -f ".env" ]; then
            source .env
            docker exec -e PGPASSWORD=$TIMESCALEDB_PASSWORD $CONTAINER_NAME \
                psql -U $TIMESCALEDB_USER -d $TIMESCALEDB_DATABASE -c "SELECT 'Connection successful!' as status;"
        else
            echo "❌ .env file not found"
        fi
        ;;

    2)
        echo ""
        echo "Resetting password to 'postgres'..."
        docker exec $CONTAINER_NAME psql -U postgres -c "ALTER USER postgres PASSWORD 'postgres';"
        echo "✅ Password reset to 'postgres'"
        echo ""
        echo "Update your .env file:"
        echo "  TIMESCALEDB_PASSWORD=postgres"
        ;;

    3)
        echo ""
        read -p "Enter new password: " newpass
        docker exec $CONTAINER_NAME psql -U postgres -c "ALTER USER postgres PASSWORD '$newpass';"
        echo "✅ Password updated to '$newpass'"
        echo ""
        echo "Update your .env file:"
        echo "  TIMESCALEDB_PASSWORD=$newpass"
        ;;

    4)
        echo ""
        echo "Last 50 lines of database logs:"
        echo "=========================================="
        docker logs --tail 50 $CONTAINER_NAME
        ;;

    5)
        echo ""
        echo "Restarting database container..."
        docker restart $CONTAINER_NAME
        sleep 3
        echo "✅ Container restarted"
        ;;

    6)
        echo ""
        read -p "⚠️  This will DELETE ALL DATA! Are you sure? (yes/no): " confirm
        if [ "$confirm" == "yes" ]; then
            echo "Removing container..."
            docker stop $CONTAINER_NAME
            docker rm $CONTAINER_NAME
            echo "Creating new container with password 'postgres'..."
            docker run -d \
                --name timescaledb \
                -p 5432:5432 \
                -e POSTGRES_PASSWORD=postgres \
                -e POSTGRES_DB=trading_bot \
                timescale/timescaledb:latest-pg14
            sleep 5
            echo "✅ New container created with password 'postgres'"
            echo "   Update your .env file: TIMESCALEDB_PASSWORD=postgres"
        else
            echo "Cancelled"
        fi
        ;;

    q)
        echo "Goodbye!"
        exit 0
        ;;

    *)
        echo "Invalid choice"
        ;;
esac

echo ""
echo "=========================================="
echo "NEXT STEPS"
echo "=========================================="
echo ""
echo "1. Make sure your .env file has the correct password"
echo "2. Run: python debug_bot.py"
echo "3. If all tests pass, run: python main.py"
echo ""
