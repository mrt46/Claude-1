"""
Database clients for the trading bot.

Provides async clients for:
- TimescaleDB (PostgreSQL with time-series extensions)
- Redis (caching and real-time data)
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import asyncpg
import redis.asyncio as redis

from src.core.logger import get_logger

logger = get_logger(__name__)


class TimescaleDBClient:
    """
    Async TimescaleDB client for time-series data storage.

    Handles:
    - OHLCV data storage
    - Trade history
    - Position tracking
    - Performance metrics
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "trading_bot",
        user: str = "postgres",
        password: str = "",
        min_connections: int = 2,
        max_connections: int = 10
    ):
        """
        Initialize TimescaleDB client.

        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            min_connections: Minimum pool connections
            max_connections: Maximum pool connections
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.min_connections = min_connections
        self.max_connections = max_connections

        self.pool: Optional[asyncpg.Pool] = None
        self._connected = False

        logger.info(f"TimescaleDBClient initialized: {host}:{port}/{database}")

    async def connect(self) -> bool:
        """
        Connect to database and create connection pool.

        Returns:
            True if connection successful, False otherwise
        """
        if self._connected and self.pool:
            return True

        try:
            self.pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                min_size=self.min_connections,
                max_size=self.max_connections,
                command_timeout=30
            )
            self._connected = True
            logger.info("TimescaleDB connection pool created")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to TimescaleDB: {e}")
            self._connected = False
            return False

    async def close(self) -> None:
        """Close database connection pool."""
        if self.pool:
            try:
                await self.pool.close()
                logger.info("TimescaleDB connection pool closed")
            except Exception as e:
                logger.error(f"Error closing TimescaleDB pool: {e}")
            finally:
                self.pool = None
                self._connected = False

    def is_connected(self) -> bool:
        """Check if connected to database."""
        return self._connected and self.pool is not None

    async def execute(self, query: str, *args) -> str:
        """
        Execute a query without returning results.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Status string
        """
        if not self.pool:
            raise RuntimeError("Database not connected")

        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """
        Execute query and fetch all results.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            List of records
        """
        if not self.pool:
            raise RuntimeError("Database not connected")

        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchone(self, query: str, *args) -> Optional[asyncpg.Record]:
        """
        Execute query and fetch single result.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Single record or None
        """
        if not self.pool:
            raise RuntimeError("Database not connected")

        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def store_ohlcv(
        self,
        symbol: str,
        interval: str,
        data: List[Dict]
    ) -> int:
        """
        Store OHLCV data.

        Args:
            symbol: Trading symbol
            interval: Candle interval (e.g., '1m', '5m', '1h')
            data: List of OHLCV records

        Returns:
            Number of records stored
        """
        if not self.pool or not data:
            return 0

        query = """
            INSERT INTO ohlcv (symbol, interval, timestamp, open, high, low, close, volume, trades)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (symbol, interval, timestamp) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                trades = EXCLUDED.trades
        """

        async with self.pool.acquire() as conn:
            count = 0
            for record in data:
                try:
                    await conn.execute(
                        query,
                        symbol,
                        interval,
                        record['timestamp'],
                        record['open'],
                        record['high'],
                        record['low'],
                        record['close'],
                        record['volume'],
                        record.get('trades', 0)
                    )
                    count += 1
                except Exception as e:
                    logger.error(f"Error storing OHLCV record: {e}")

            return count

    async def get_ohlcv(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Dict]:
        """
        Retrieve OHLCV data.

        Args:
            symbol: Trading symbol
            interval: Candle interval
            start_time: Start timestamp
            end_time: End timestamp (default: now)
            limit: Maximum records to return

        Returns:
            List of OHLCV records
        """
        if not self.pool:
            return []

        if end_time is None:
            end_time = datetime.now(timezone.utc)

        query = """
            SELECT timestamp, open, high, low, close, volume, trades
            FROM ohlcv
            WHERE symbol = $1 AND interval = $2
            AND timestamp >= $3 AND timestamp <= $4
            ORDER BY timestamp ASC
            LIMIT $5
        """

        records = await self.fetch(query, symbol, interval, start_time, end_time, limit)

        return [
            {
                'timestamp': r['timestamp'],
                'open': float(r['open']),
                'high': float(r['high']),
                'low': float(r['low']),
                'close': float(r['close']),
                'volume': float(r['volume']),
                'trades': r['trades']
            }
            for r in records
        ]

    async def initialize_schema(self) -> bool:
        """
        Initialize database schema (create tables if not exist).

        Returns:
            True if successful
        """
        if not self.pool:
            logger.error("Database not connected")
            return False

        try:
            async with self.pool.acquire() as conn:
                # Trades table (completed trades with PnL)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS trades (
                        id TEXT PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL,
                        entry_price NUMERIC NOT NULL,
                        exit_price NUMERIC NOT NULL,
                        quantity NUMERIC NOT NULL,
                        position_value_usdt NUMERIC NOT NULL,
                        stop_loss NUMERIC,
                        take_profit NUMERIC,
                        trailing_stop BOOLEAN DEFAULT FALSE,
                        pnl NUMERIC NOT NULL,
                        pnl_percent NUMERIC NOT NULL,
                        entry_fee NUMERIC NOT NULL,
                        exit_fee NUMERIC NOT NULL,
                        total_fees NUMERIC NOT NULL,
                        closure_reason TEXT NOT NULL,
                        strategy_name TEXT,
                        entry_time TIMESTAMPTZ NOT NULL,
                        exit_time TIMESTAMPTZ NOT NULL,
                        hold_duration_seconds INTEGER NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)

                # Index for fast queries
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_trades_exit_time
                    ON trades(exit_time DESC)
                """)

                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_trades_symbol
                    ON trades(symbol, exit_time DESC)
                """)

                # Positions table (open positions)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS positions (
                        id TEXT PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL,
                        entry_price NUMERIC NOT NULL,
                        quantity NUMERIC NOT NULL,
                        position_value_usdt NUMERIC NOT NULL,
                        stop_loss NUMERIC,
                        take_profit NUMERIC,
                        trailing_stop_percent NUMERIC,
                        max_price NUMERIC,
                        min_price NUMERIC,
                        unrealized_pnl NUMERIC DEFAULT 0,
                        unrealized_pnl_percent NUMERIC DEFAULT 0,
                        strategy_name TEXT,
                        opened_at TIMESTAMPTZ NOT NULL,
                        partial_fill BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)

                # OHLCV table (if not exists)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS ohlcv (
                        symbol TEXT NOT NULL,
                        interval TEXT NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL,
                        open NUMERIC NOT NULL,
                        high NUMERIC NOT NULL,
                        low NUMERIC NOT NULL,
                        close NUMERIC NOT NULL,
                        volume NUMERIC NOT NULL,
                        trades INTEGER DEFAULT 0,
                        PRIMARY KEY (symbol, interval, timestamp)
                    )
                """)

                logger.info("Database schema initialized successfully")
                return True

        except Exception as e:
            logger.error(f"Error initializing schema: {e}")
            return False

    async def store_completed_trade(self, trade: Dict) -> bool:
        """
        Store a completed trade record with PnL.

        Args:
            trade: Trade data dictionary with keys:
                - id, symbol, side, entry_price, exit_price, quantity
                - position_value_usdt, stop_loss, take_profit, trailing_stop
                - pnl, pnl_percent, entry_fee, exit_fee, total_fees
                - closure_reason, strategy_name, entry_time, exit_time
                - hold_duration_seconds

        Returns:
            True if successful
        """
        if not self.pool:
            return False

        query = """
            INSERT INTO trades (
                id, symbol, side, entry_price, exit_price, quantity,
                position_value_usdt, stop_loss, take_profit, trailing_stop,
                pnl, pnl_percent, entry_fee, exit_fee, total_fees,
                closure_reason, strategy_name, entry_time, exit_time,
                hold_duration_seconds
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20
            )
        """

        try:
            await self.execute(
                query,
                trade['id'],
                trade['symbol'],
                trade['side'],
                trade['entry_price'],
                trade['exit_price'],
                trade['quantity'],
                trade['position_value_usdt'],
                trade.get('stop_loss'),
                trade.get('take_profit'),
                trade.get('trailing_stop', False),
                trade['pnl'],
                trade['pnl_percent'],
                trade['entry_fee'],
                trade['exit_fee'],
                trade['total_fees'],
                trade['closure_reason'],
                trade.get('strategy_name'),
                trade['entry_time'],
                trade['exit_time'],
                trade['hold_duration_seconds']
            )
            logger.info(
                f"Trade stored: {trade['symbol']} {trade['side']} "
                f"PnL: ${trade['pnl']:.2f} ({trade['pnl_percent']:+.2f}%)"
            )
            return True
        except Exception as e:
            logger.error(f"Error storing completed trade: {e}")
            return False

    async def get_recent_trades(self, limit: int = 20, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get recent completed trades.

        Args:
            limit: Maximum number of trades to return
            symbol: Filter by symbol (optional)

        Returns:
            List of trade records
        """
        if not self.pool:
            return []

        if symbol:
            query = """
                SELECT * FROM trades
                WHERE symbol = $1
                ORDER BY exit_time DESC
                LIMIT $2
            """
            records = await self.fetch(query, symbol, limit)
        else:
            query = """
                SELECT * FROM trades
                ORDER BY exit_time DESC
                LIMIT $1
            """
            records = await self.fetch(query, limit)

        return [dict(r) for r in records]

    async def get_daily_stats(self) -> Dict:
        """
        Get today's trading statistics.

        Returns:
            Dictionary with:
            - total_trades, winning_trades, losing_trades, win_rate
            - total_pnl, total_fees, net_pnl
            - avg_hold_duration_minutes
        """
        if not self.pool:
            return {}

        query = """
            SELECT
                COUNT(*) as total_trades,
                COUNT(*) FILTER (WHERE pnl > 0) as winning_trades,
                COUNT(*) FILTER (WHERE pnl < 0) as losing_trades,
                COALESCE(SUM(pnl), 0) as total_pnl,
                COALESCE(SUM(total_fees), 0) as total_fees,
                COALESCE(AVG(hold_duration_seconds), 0) as avg_hold_seconds
            FROM trades
            WHERE exit_time >= CURRENT_DATE
        """

        try:
            record = await self.fetchone(query)
            if not record:
                return {}

            total = record['total_trades']
            winning = record['winning_trades']

            return {
                'total_trades': total,
                'winning_trades': winning,
                'losing_trades': record['losing_trades'],
                'win_rate': (winning / total * 100) if total > 0 else 0.0,
                'total_pnl': float(record['total_pnl']),
                'total_fees': float(record['total_fees']),
                'net_pnl': float(record['total_pnl']),
                'avg_hold_duration_minutes': int(record['avg_hold_seconds'] / 60)
            }
        except Exception as e:
            logger.error(f"Error getting daily stats: {e}")
            return {}


class RedisClient:
    """
    Async Redis client for caching and real-time data.

    Handles:
    - Real-time price caching
    - Order book snapshots
    - Signal deduplication
    - Rate limiting
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: Optional[str] = None,
        db: int = 0,
        decode_responses: bool = True
    ):
        """
        Initialize Redis client.

        Args:
            host: Redis host
            port: Redis port
            password: Redis password (optional)
            db: Redis database number
            decode_responses: Decode responses to strings
        """
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self.decode_responses = decode_responses

        self.client: Optional[redis.Redis] = None
        self._connected = False

        logger.info(f"RedisClient initialized: {host}:{port}/db{db}")

    async def connect(self) -> bool:
        """
        Connect to Redis.

        Returns:
            True if connection successful, False otherwise
        """
        if self._connected and self.client:
            return True

        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                db=self.db,
                decode_responses=self.decode_responses
            )

            # Test connection
            await self.client.ping()
            self._connected = True
            logger.info("Redis connection established")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        if self.client:
            try:
                await self.client.close()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")
            finally:
                self.client = None
                self._connected = False

    def is_connected(self) -> bool:
        """Check if connected to Redis."""
        return self._connected and self.client is not None

    async def get(self, key: str) -> Optional[str]:
        """
        Get value by key.

        Args:
            key: Redis key

        Returns:
            Value or None
        """
        if not self.client:
            return None
        return await self.client.get(key)

    async def set(
        self,
        key: str,
        value: Union[str, bytes, int, float],
        expire: Optional[int] = None
    ) -> bool:
        """
        Set key-value pair.

        Args:
            key: Redis key
            value: Value to store
            expire: Expiration time in seconds (optional)

        Returns:
            True if successful
        """
        if not self.client:
            return False

        try:
            if expire:
                await self.client.setex(key, expire, value)
            else:
                await self.client.set(key, value)
            return True
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete key.

        Args:
            key: Redis key

        Returns:
            True if key was deleted
        """
        if not self.client:
            return False
        result = await self.client.delete(key)
        return result > 0

    async def exists(self, key: str) -> bool:
        """
        Check if key exists.

        Args:
            key: Redis key

        Returns:
            True if key exists
        """
        if not self.client:
            return False
        return await self.client.exists(key) > 0

    async def hset(self, name: str, key: str, value: Any) -> bool:
        """
        Set hash field.

        Args:
            name: Hash name
            key: Field key
            value: Field value

        Returns:
            True if successful
        """
        if not self.client:
            return False
        try:
            await self.client.hset(name, key, value)
            return True
        except Exception as e:
            logger.error(f"Redis hset error: {e}")
            return False

    async def hget(self, name: str, key: str) -> Optional[str]:
        """
        Get hash field.

        Args:
            name: Hash name
            key: Field key

        Returns:
            Field value or None
        """
        if not self.client:
            return None
        return await self.client.hget(name, key)

    async def hgetall(self, name: str) -> Dict[str, str]:
        """
        Get all hash fields.

        Args:
            name: Hash name

        Returns:
            Dictionary of field-value pairs
        """
        if not self.client:
            return {}
        return await self.client.hgetall(name)

    async def cache_price(self, symbol: str, price: float, expire: int = 60) -> bool:
        """
        Cache current price for symbol.

        Args:
            symbol: Trading symbol
            price: Current price
            expire: Cache expiration in seconds

        Returns:
            True if successful
        """
        key = f"price:{symbol}"
        return await self.set(key, str(price), expire)

    async def get_cached_price(self, symbol: str) -> Optional[float]:
        """
        Get cached price for symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Cached price or None
        """
        key = f"price:{symbol}"
        value = await self.get(key)
        if value:
            return float(value)
        return None

    async def cache_orderbook(
        self,
        symbol: str,
        orderbook: Dict,
        expire: int = 5
    ) -> bool:
        """
        Cache order book snapshot.

        Args:
            symbol: Trading symbol
            orderbook: Order book data
            expire: Cache expiration in seconds

        Returns:
            True if successful
        """
        import json
        key = f"orderbook:{symbol}"
        return await self.set(key, json.dumps(orderbook), expire)

    async def get_cached_orderbook(self, symbol: str) -> Optional[Dict]:
        """
        Get cached order book.

        Args:
            symbol: Trading symbol

        Returns:
            Order book data or None
        """
        import json
        key = f"orderbook:{symbol}"
        value = await self.get(key)
        if value:
            return json.loads(value)
        return None

    async def check_signal_processed(
        self,
        signal_id: str,
        window_seconds: int = 300
    ) -> bool:
        """
        Check if signal was already processed (for deduplication).

        Args:
            signal_id: Unique signal identifier
            window_seconds: Deduplication window

        Returns:
            True if signal was already processed
        """
        key = f"signal:{signal_id}"
        return await self.exists(key)

    async def mark_signal_processed(
        self,
        signal_id: str,
        window_seconds: int = 300
    ) -> bool:
        """
        Mark signal as processed.

        Args:
            signal_id: Unique signal identifier
            window_seconds: Time window for deduplication

        Returns:
            True if successful
        """
        key = f"signal:{signal_id}"
        return await self.set(key, "1", window_seconds)
