"""
Debug script to diagnose why bot is not trading.

Run this to check:
1. Database connections
2. Exchange connectivity
3. Symbol validation
4. Signal generation capability
"""

import asyncio
import sys
from pathlib import Path

from src.core.config import Config
from src.core.exchange import BinanceExchange
from src.data.database import RedisClient, TimescaleDBClient
from src.data.market_data import MarketDataManager
from src.strategies.institutional import InstitutionalStrategy


async def test_database_connection():
    """Test database connections."""
    print("\n" + "="*60)
    print("1. TESTING DATABASE CONNECTIONS")
    print("="*60)

    config = Config()

    # Test TimescaleDB
    print("\n[TimescaleDB]")
    try:
        db = TimescaleDBClient(
            host=config.database.timescaledb_host,
            port=config.database.timescaledb_port,
            database=config.database.timescaledb_database,
            user=config.database.timescaledb_user,
            password=config.database.timescaledb_password
        )
        connected = await db.connect()
        if connected:
            print(f"✅ Connected to TimescaleDB at {config.database.timescaledb_host}:{config.database.timescaledb_port}")
            await db.close()
        else:
            print(f"❌ Failed to connect to TimescaleDB")
            print(f"   Host: {config.database.timescaledb_host}")
            print(f"   Port: {config.database.timescaledb_port}")
            print(f"   Database: {config.database.timescaledb_database}")
            print(f"   User: {config.database.timescaledb_user}")
            print(f"   Password: {'*' * len(config.database.timescaledb_password)}")
    except Exception as e:
        print(f"❌ TimescaleDB error: {e}")

    # Test Redis
    print("\n[Redis]")
    try:
        redis = RedisClient(
            host=config.database.redis_host,
            port=config.database.redis_port,
            password=config.database.redis_password,
            db=config.database.redis_db
        )
        connected = await redis.connect()
        if connected:
            print(f"✅ Connected to Redis at {config.database.redis_host}:{config.database.redis_port}")
            await redis.close()
        else:
            print(f"❌ Failed to connect to Redis")
    except Exception as e:
        print(f"❌ Redis error: {e}")


async def test_exchange_connection():
    """Test exchange connectivity and symbols."""
    print("\n" + "="*60)
    print("2. TESTING EXCHANGE CONNECTION")
    print("="*60)

    config = Config()

    print(f"\n[Testnet: {config.exchange.testnet}]")

    try:
        exchange = BinanceExchange(
            api_key=config.exchange.api_key,
            api_secret=config.exchange.api_secret,
            testnet=config.exchange.testnet
        )

        async with exchange:
            # Test account access
            print("\n[Account Info]")
            try:
                balance = await exchange.get_balance("USDT")
                print(f"✅ USDT Balance: {balance:.2f}")
            except Exception as e:
                print(f"❌ Failed to get balance: {e}")

            # Test symbols
            print(f"\n[Testing Symbols: {', '.join(config.trading.symbols)}]")
            valid_symbols = []
            invalid_symbols = []

            for symbol in config.trading.symbols:
                try:
                    price = await exchange.get_current_price(symbol)
                    if price:
                        print(f"✅ {symbol}: ${price:,.2f}")
                        valid_symbols.append(symbol)
                    else:
                        print(f"❌ {symbol}: No price returned")
                        invalid_symbols.append(symbol)
                except Exception as e:
                    print(f"❌ {symbol}: {e}")
                    invalid_symbols.append(symbol)

            print(f"\nSummary: {len(valid_symbols)} valid, {len(invalid_symbols)} invalid")

            if invalid_symbols:
                print(f"⚠️  Invalid symbols: {', '.join(invalid_symbols)}")
                print("   Consider removing these from .env TRADING_SYMBOLS")

            return valid_symbols

    except Exception as e:
        print(f"❌ Exchange connection failed: {e}")
        return []


async def test_signal_generation(valid_symbols):
    """Test if strategy can generate signals."""
    print("\n" + "="*60)
    print("3. TESTING SIGNAL GENERATION")
    print("="*60)

    if not valid_symbols:
        print("❌ No valid symbols to test")
        return

    config = Config()

    try:
        # Initialize components
        market_data = MarketDataManager(testnet=config.exchange.testnet)
        strategy = InstitutionalStrategy({
            'min_score': config.strategy.min_score,
            'min_buy_score': config.strategy.min_buy_score,
            'min_sell_score': config.strategy.min_sell_score,
            'weights': config.strategy.weights
        })
        strategy.set_market_data_manager(market_data)

        exchange = BinanceExchange(
            api_key=config.exchange.api_key,
            api_secret=config.exchange.api_secret,
            testnet=config.exchange.testnet
        )

        async with exchange:
            # Test first valid symbol
            test_symbol = valid_symbols[0]
            print(f"\n[Testing {test_symbol}]")

            # Get OHLCV data
            print("Fetching OHLCV data...")
            try:
                df = await market_data.get_ohlcv_data(test_symbol, interval="1m", limit=200)

                if df.empty:
                    print(f"❌ No OHLCV data returned for {test_symbol}")
                    return

                print(f"✅ Got {len(df)} candles")
                print(f"   Latest price: ${df['close'].iloc[-1]:,.2f}")
                print(f"   Time range: {df.index[0]} to {df.index[-1]}")

                # Try to generate signal
                print("\nGenerating signal...")
                signal = await strategy.generate_signal(df)

                if signal:
                    print(f"✅ SIGNAL GENERATED!")
                    print(f"   Side: {signal.side}")
                    print(f"   Entry: ${signal.entry_price:,.2f}")
                    print(f"   Stop Loss: ${signal.stop_loss:,.2f}")
                    print(f"   Take Profit: ${signal.take_profit:,.2f}")
                    print(f"   Confidence: {signal.confidence:.2%}")
                else:
                    print(f"⚠️  No signal generated (scores below threshold)")
                    print(f"   This is NORMAL - strategy is selective")
                    print(f"   Min score required: {config.strategy.min_score}")

                    # Check last scores from strategy
                    if hasattr(strategy, '_last_buy_score'):
                        print(f"   Last BUY score: {strategy._last_buy_score:.1f}/{strategy._last_max_score:.1f}")
                        print(f"   Last SELL score: {strategy._last_sell_score:.1f}/{strategy._last_max_score:.1f}")

            except Exception as e:
                print(f"❌ Signal generation failed: {e}")
                import traceback
                traceback.print_exc()

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


async def test_main_loop_entry():
    """Test if main loop can start."""
    print("\n" + "="*60)
    print("4. TESTING MAIN LOOP ENTRY")
    print("="*60)

    print("\n[Checking bot.run() method]")

    try:
        from main import TradingBot

        bot = TradingBot()

        # Check if bot has run method
        if hasattr(bot, 'run'):
            print("✅ bot.run() method exists")
        else:
            print("❌ bot.run() method not found")

        # Check if bot has initialize method
        if hasattr(bot, 'initialize'):
            print("✅ bot.initialize() method exists")
        else:
            print("❌ bot.initialize() method not found")

        print("\n[Recommendation]")
        print("Run bot with verbose logging to see if main loop starts:")
        print("  python main.py")
        print("\nLook for this log message:")
        print("  'Trading bot STARTED - Entering main loop'")

    except Exception as e:
        print(f"❌ Import failed: {e}")


async def main():
    """Run all diagnostic tests."""
    print("\n" + "="*60)
    print("BOT DIAGNOSTIC TOOL")
    print("="*60)
    print("This will test why your bot is not trading.\n")

    try:
        # Test 1: Database
        await test_database_connection()

        # Test 2: Exchange & Symbols
        valid_symbols = await test_exchange_connection()

        # Test 3: Signal Generation
        if valid_symbols:
            await test_signal_generation(valid_symbols)
        else:
            print("\n❌ Skipping signal generation test (no valid symbols)")

        # Test 4: Main Loop
        await test_main_loop_entry()

        # Summary
        print("\n" + "="*60)
        print("DIAGNOSTIC COMPLETE")
        print("="*60)
        print("\n[Next Steps]")
        print("1. Fix any ❌ errors shown above")
        print("2. If database password is wrong, update .env file")
        print("3. If symbols are invalid on testnet, update TRADING_SYMBOLS in .env")
        print("4. Run bot again: python main.py")
        print("5. Check logs for 'Trading bot STARTED - Entering main loop'")
        print("\n[Understanding Results]")
        print("- No signal generated = NORMAL (strategy is selective)")
        print("- Wait for market conditions to meet min_score threshold")
        print("- Bot needs to see 7/10 score to trade (very conservative)")

    except KeyboardInterrupt:
        print("\n\nDiagnostic cancelled by user")
    except Exception as e:
        print(f"\n\n❌ Diagnostic failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nExiting...")
