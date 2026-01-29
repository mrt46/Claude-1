#!/bin/bash
# Database Setup Script for Linux/Mac
# This script sets up TimescaleDB and Redis using Docker

echo "🏛️  Trading Bot Database Setup"
echo ""

# Check if Docker is installed
echo "Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed!"
    echo "Please install Docker from: https://www.docker.com/get-started"
    exit 1
fi
echo "✅ Docker found: $(docker --version)"

# Check if Docker is running
echo "Checking if Docker is running..."
if ! docker ps &> /dev/null; then
    echo "❌ Docker is not running!"
    echo "Please start Docker and try again"
    exit 1
fi
echo "✅ Docker is running"

# Check if docker-compose is available
echo "Checking docker-compose..."
if command -v docker-compose &> /dev/null; then
    echo "✅ Docker Compose found: $(docker-compose --version)"
    USE_COMPOSE_V2=false
elif docker compose version &> /dev/null; then
    echo "✅ Docker Compose (v2) found"
    USE_COMPOSE_V2=true
else
    echo "❌ Docker Compose not found!"
    exit 1
fi

echo ""
echo "Starting database containers..."

# Navigate to project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Start containers
if [ "$USE_COMPOSE_V2" = true ]; then
    docker compose up -d
else
    docker-compose up -d
fi

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Database containers started successfully!"
    echo ""
    echo "Waiting for databases to be ready..."
    
    # Wait for TimescaleDB
    echo -n "Waiting for TimescaleDB"
    for i in {1..15}; do
        if docker exec trading_bot_timescaledb pg_isready -U postgres &> /dev/null; then
            echo ""
            echo "✅ TimescaleDB is ready"
            break
        fi
        echo -n "."
        sleep 2
    done
    echo ""
    
    # Wait for Redis
    if docker exec trading_bot_redis redis-cli ping &> /dev/null; then
        echo "✅ Redis is ready"
    else
        echo "⚠️  Redis might still be starting..."
    fi
    
    echo ""
    echo "📊 Database Status:"
    echo "  TimescaleDB: localhost:5432"
    echo "  Redis: localhost:6379"
    echo ""
    echo "💡 Update your .env file with:"
    echo "  TIMESCALEDB_HOST=localhost"
    echo "  TIMESCALEDB_PORT=5432"
    echo "  TIMESCALEDB_DATABASE=trading_bot"
    echo "  TIMESCALEDB_USER=postgres"
    echo "  TIMESCALEDB_PASSWORD=postgres"
    echo ""
    echo "  REDIS_HOST=localhost"
    echo "  REDIS_PORT=6379"
    echo ""
    echo "✅ Setup complete! You can now run the bot."
else
    echo ""
    echo "❌ Failed to start containers!"
    echo "Check Docker logs: docker-compose logs"
    exit 1
fi
