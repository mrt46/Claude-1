#!/bin/bash
# Database Schema Reset Script

echo "=========================================="
echo "DATABASE SCHEMA RESET"
echo "=========================================="
echo ""
echo "⚠️  WARNING: This will DELETE all trade history!"
echo ""
read -p "Are you sure you want to continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Resetting database schema..."

# Drop and recreate database
docker exec trading_bot_timescaledb psql -U postgres -c "DROP DATABASE IF EXISTS trading_bot;"
docker exec trading_bot_timescaledb psql -U postgres -c "CREATE DATABASE trading_bot;"

echo "✅ Database recreated"
echo ""
echo "Schema will be automatically initialized when bot starts."
echo ""
echo "Run: python main.py"
