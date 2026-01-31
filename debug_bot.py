"""
Debug script to diagnose why bot is not trading.

Run this to check:
1. Database connections
2. Exchange connectivity
3. Symbol validation
4. Signal generation capability
"""

import asyncio
import os
import sys
from pathlib import Path

# Check if .env exists
env_file = Path(".env")
if not env_file.exists():
    print("⚠️  .env file not found!")
    print("Creating a template .env file...")
    template = """# Exchange API
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
TESTNET=true

# Trading Configuration
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT

# Database Configuration
TIMESCALEDB_HOST=localhost
TIMESCALEDB_PORT=5432
TIMESCALEDB_DATABASE=trading_bot
TIMESCALEDB_USER=postgres
TIMESCALEDB_PASSWORD=postgres

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
"""
    with open(".env", "w") as f:
        f.write(template)
    print("✅ Created .env template. Please update it with your actual values.")
    print("")


async def test_database_connection():
    """Test database connections."""
    print("\n" + "="*60)
    print("1. TESTING DATABASE CONNECTIONS")
    print("="*60)

    # Test TimescaleDB
    print("\n[TimescaleDB]")
    try:
        from src.data.database import TimescaleDBClient

        host = os.getenv("TIMESCALEDB_HOST", "localhost")
        port = int(os.getenv("TIMESCALEDB_PORT", "5432"))
        database = os.getenv("TIMESCALEDB_DATABASE", "trading_bot")
        user = os.getenv("TIMESCALEDB_USER", "postgres")
        password = os.getenv("TIMESCALEDB_PASSWORD", "postgres")

        print(f"Connection details:")
        print(f"  Host: {host}:{port}")
        print(f"  Database: {database}")
        print(f"  User: {user}")
        print(f"  Password: {'*' * len(password) if password else '(empty)'}")

        db = TimescaleDBClient(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        connected = await db.connect()
        if connected:
            print(f"✅ Connected to TimescaleDB successfully!")

            # Test schema
            try:
                schema_ok = await db.initialize_schema()
                if schema_ok:
                    print("✅ Database schema is ready")
                else:
                    print("⚠️  Schema initialization had issues (but connection works)")
            except Exception as e:
                print(f"⚠️  Schema check failed: {e}")

            await db.close()
        else:
            print(f"❌ Failed to connect to TimescaleDB")
            print("\n💡 Troubleshooting:")
            print("  1. Check if Docker container is running:")
            print("     docker ps | grep timescaledb")
            print("  2. Check password in .env file")
            print("  3. Try resetting password:")
            print("     docker exec -it timescaledb psql -U postgres")
            print("     ALTER USER postgres PASSWORD 'your_password';")
            return False
    except Exception as e:
        print(f"❌ TimescaleDB test error: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test Redis
    print("\n[Redis]")
    try:
        from src.data.database import RedisClient

        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        password = os.getenv("REDIS_PASSWORD", "")
        db = int(os.getenv("REDIS_DB", "0"))

        redis = RedisClient(
            host=host,
            port=port,
            password=password if password else None,
            db=db
        )
        connected = await redis.connect()
        if connected:
            print(f"✅ Connected to Redis at {host}:{port}")
            await redis.close()
            return True
        else:
            print(f"❌ Failed to connect to Redis")
            return False
    except Exception as e:
        print(f"❌ Redis error: {e}")
        return False


async def test_exchange_connection():
    """Test exchange connectivity and symbols."""
    print("\n" + "="*60)
    print("2. TESTING EXCHANGE CONNECTION")
    print("="*60)

    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    testnet = os.getenv("TESTNET", "true").lower() == "true"

    if not api_key or not api_secret or "your_api" in api_key.lower():
        print("❌ Binance API keys not configured in .env")
        print("\n💡 To test exchange connection:")
        print("  1. Get API keys from Binance")
        print("  2. Update .env file with your keys")
        print("  3. Run this script again")
        return []

    print(f"\n[Testnet: {testnet}]")

    try:
        from src.core.exchange import BinanceExchange

        exchange = BinanceExchange(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet
        )

        async with exchange:
            # Test account access
            print("\n[Account Info]")
            try:
                balance = await exchange.get_balance("USDT")
                print(f"✅ USDT Balance: {balance:.2f}")
            except Exception as e:
                print(f"❌ Failed to get balance: {e}")
                return []

            # Test symbols
            symbols_str = os.getenv("TRADING_SYMBOLS", "BTCUSDT,ETHUSDT,BNBUSDT")
            symbols = [s.strip() for s in symbols_str.split(",")]

            print(f"\n[Testing Symbols: {', '.join(symbols)}]")
            valid_symbols = []
            invalid_symbols = []

            for symbol in symbols:
                try:
                    price = await exchange.get_current_price(symbol)
                    if price:
                        print(f"✅ {symbol}: ${price:,.2f}")
                        valid_symbols.append(symbol)
                    else:
                        print(f"❌ {symbol}: No price returned")
                        invalid_symbols.append(symbol)
                except Exception as e:
                    print(f"❌ {symbol}: {str(e)[:50]}")
                    invalid_symbols.append(symbol)

            print(f"\nSummary: {len(valid_symbols)} valid, {len(invalid_symbols)} invalid")

            if invalid_symbols:
                print(f"\n⚠️  Invalid symbols on {'testnet' if testnet else 'mainnet'}: {', '.join(invalid_symbols)}")
                print("💡 Update TRADING_SYMBOLS in .env to remove invalid symbols")

            return valid_symbols

    except Exception as e:
        print(f"❌ Exchange connection failed: {e}")
        import traceback
        traceback.print_exc()
        return []


async def check_environment():
    """Check environment configuration."""
    print("\n" + "="*60)
    print("3. CHECKING ENVIRONMENT CONFIGURATION")
    print("="*60)

    required_vars = [
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "TIMESCALEDB_HOST",
        "TIMESCALEDB_PASSWORD",
        "TRADING_SYMBOLS"
    ]

    missing = []
    configured = []

    for var in required_vars:
        value = os.getenv(var, "")
        if not value or "your_" in value.lower():
            missing.append(var)
            print(f"❌ {var}: Not configured")
        else:
            configured.append(var)
            if "SECRET" in var or "PASSWORD" in var:
                print(f"✅ {var}: {'*' * 10}")
            else:
                display_value = value if len(value) < 50 else value[:47] + "..."
                print(f"✅ {var}: {display_value}")

    print(f"\nSummary: {len(configured)}/{len(required_vars)} required variables configured")

    if missing:
        print(f"\n⚠️  Missing configuration:")
        for var in missing:
            print(f"  - {var}")
        print("\n💡 Update .env file with these values")
        return False

    return True


async def test_strategy_config():
    """Test strategy configuration."""
    print("\n" + "="*60)
    print("4. CHECKING STRATEGY CONFIGURATION")
    print("="*60)

    try:
        min_score = float(os.getenv("MIN_SCORE", "7.0"))
        print(f"\n[Strategy Settings]")
        print(f"Min Score Threshold: {min_score}/10.0")

        if min_score >= 8.0:
            print("⚠️  Very strict threshold - trades will be rare")
            print("   Consider lowering to 6.5-7.5 for more opportunities")
        elif min_score <= 5.0:
            print("⚠️  Very loose threshold - may result in poor quality trades")
            print("   Consider raising to 6.5-7.5 for better quality")
        else:
            print("✅ Threshold is in recommended range (6.5-7.5)")

        print(f"\n💡 Understanding Min Score:")
        print(f"  - Score is calculated from 5 factors (Volume Profile, Order Book, CVD, S/D zones, HVN)")
        print(f"  - Each factor contributes points (max 10 total)")
        print(f"  - Higher threshold = fewer but higher quality trades")
        print(f"  - Current: Requires {min_score}/10 factors to align")

        return True

    except Exception as e:
        print(f"❌ Strategy config error: {e}")
        return False


async def main():
    """Run all diagnostic tests."""
    print("\n" + "="*60)
    print("BOT DIAGNOSTIC TOOL")
    print("="*60)
    print("This will test why your bot is not trading.\n")

    results = {
        "environment": False,
        "database": False,
        "exchange": False,
        "strategy": False
    }

    try:
        # Test 1: Environment
        results["environment"] = await check_environment()

        # Test 2: Database (always test, doesn't need API keys)
        results["database"] = await test_database_connection()

        # Test 3: Strategy Config
        results["strategy"] = await test_strategy_config()

        # Test 4: Exchange & Symbols (only if API keys configured)
        if results["environment"]:
            valid_symbols = await test_exchange_connection()
            results["exchange"] = len(valid_symbols) > 0
        else:
            print("\n⏭️  Skipping exchange test (API keys not configured)")

        # Summary
        print("\n" + "="*60)
        print("DIAGNOSTIC SUMMARY")
        print("="*60)

        passed = sum(1 for v in results.values() if v)
        total = len(results)

        status_emoji = "✅" if passed == total else "⚠️" if passed > 0 else "❌"
        print(f"\n{status_emoji} {passed}/{total} checks passed")

        for test, passed in results.items():
            emoji = "✅" if passed else "❌"
            print(f"  {emoji} {test.capitalize()}")

        # Next steps
        print("\n" + "="*60)
        print("NEXT STEPS")
        print("="*60)

        if not results["database"]:
            print("\n🔧 DATABASE ISSUES DETECTED")
            print("  Fix steps:")
            print("  1. Start Docker containers:")
            print("     docker-compose up -d")
            print("  2. Wait 5 seconds for database to initialize")
            print("  3. Check .env file has correct password")
            print("  4. Run this script again")

        elif not results["environment"]:
            print("\n🔧 CONFIGURATION INCOMPLETE")
            print("  Update .env file with:")
            print("  - Binance API keys")
            print("  - Trading symbols")
            print("  Then run this script again")

        elif not results["exchange"]:
            print("\n🔧 EXCHANGE CONNECTION ISSUES")
            print("  Check:")
            print("  - API keys are correct")
            print("  - Symbols are valid on testnet/mainnet")
            print("  - Network connection is working")

        else:
            print("\n✅ ALL SYSTEMS READY!")
            print("\n🚀 Your bot should be working. Run:")
            print("     python main.py")
            print("\n📊 The dashboard will appear in full-screen mode")
            print("   - Log messages will be hidden by dashboard")
            print("   - This is normal - dashboard shows all info")
            print("\n💡 Understanding 'No Trades':")
            print("   - Strategy is very selective (min score 7/10)")
            print("   - May take hours/days to find good opportunities")
            print("   - Dashboard shows analysis scores in real-time")
            print("   - Check 'Bot Activity' panel for last analysis results")

    except KeyboardInterrupt:
        print("\n\nDiagnostic cancelled by user")
    except Exception as e:
        print(f"\n\n❌ Diagnostic failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Load .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("⚠️  python-dotenv not installed, using system environment variables")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nExiting...")
