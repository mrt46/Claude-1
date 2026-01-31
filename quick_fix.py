"""
Quick fix script to repair database and test WebSocket.

Run this before starting the bot.
"""
import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def fix_database_schema():
    """Fix database schema by adding missing columns."""
    print("=" * 60)
    print("FIXING DATABASE SCHEMA")
    print("=" * 60)

    from src.data.database import TimescaleDBClient

    # Get credentials from environment
    host = os.getenv("TIMESCALEDB_HOST", "localhost")
    port = int(os.getenv("TIMESCALEDB_PORT", "5432"))
    database = os.getenv("TIMESCALEDB_DATABASE", "trading_bot")
    user = os.getenv("TIMESCALEDB_USER", "postgres")
    password = os.getenv("TIMESCALEDB_PASSWORD", "postgres")

    print(f"\nConnecting to {host}:{port}/{database}...")

    db = TimescaleDBClient(host, port, database, user, password)

    try:
        connected = await db.connect()
        if not connected:
            print("❌ Failed to connect to database")
            return False

        print("✅ Connected to database")

        # Drop existing trades table if it has wrong schema
        print("\nDropping existing trades table...")
        await db.pool.execute("DROP TABLE IF EXISTS trades;")
        print("✅ Dropped trades table")

        # Recreate with correct schema
        print("\nRecreating trades table with correct schema...")
        schema_ok = await db.initialize_schema()

        if schema_ok:
            print("✅ Database schema fixed!")
            return True
        else:
            print("❌ Schema initialization failed")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await db.close()


async def test_websocket():
    """Test WebSocket connection."""
    print("\n" + "=" * 60)
    print("TESTING WEBSOCKET")
    print("=" * 60)

    from src.data.market_data import MarketDataManager

    testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    print(f"\nTestnet: {testnet}")

    try:
        manager = MarketDataManager(testnet=testnet)

        # Test connection with a simple symbol
        print("\nTesting WebSocket connection to BTCUSDT...")

        connected = False

        def on_connect(data):
            nonlocal connected
            print(f"✅ WebSocket connected: {data}")
            connected = True

        # Try to connect
        await manager.ws_manager.connect_kline_stream(
            symbol="BTCUSDT",
            interval="1m",
            callback=on_connect
        )

        # Wait a bit
        await asyncio.sleep(3)

        if connected:
            print("✅ WebSocket is working!")
        else:
            print("⚠️  WebSocket connected but no callback received")

        # Disconnect
        await manager.ws_manager.disconnect_all()

        return True

    except Exception as e:
        print(f"❌ WebSocket test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all fixes."""
    print("\n" + "=" * 60)
    print("QUICK FIX TOOL")
    print("=" * 60)
    print("\nThis will:")
    print("1. Fix database schema (drop and recreate trades table)")
    print("2. Test WebSocket connection")
    print("")

    # Load environment
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ Loaded .env file")
    except:
        print("⚠️  .env file not loaded")

    # Fix database
    db_ok = await fix_database_schema()

    # Test WebSocket
    ws_ok = await test_websocket()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"\nDatabase: {'✅ FIXED' if db_ok else '❌ FAILED'}")
    print(f"WebSocket: {'✅ WORKING' if ws_ok else '❌ FAILED'}")

    if db_ok and ws_ok:
        print("\n✅ ALL FIXES APPLIED SUCCESSFULLY!")
        print("\nYou can now run the bot:")
        print("  python main.py")
    else:
        print("\n❌ SOME FIXES FAILED")
        print("\nCheck the errors above and try again.")

    print("")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
