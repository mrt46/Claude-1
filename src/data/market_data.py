"""
Market data management for the trading bot.

Provides:
- REST API client for historical data
- WebSocket manager for real-time streams
- MarketDataManager for unified access
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Set

import aiohttp
import pandas as pd
import websockets
from websockets.exceptions import ConnectionClosed

from src.core.logger import get_logger
from src.data.normalization import normalize_ohlcv_data, normalize_symbol

logger = get_logger(__name__)


# Binance API endpoints
BINANCE_REST_URL = "https://api.binance.com"
BINANCE_TESTNET_REST_URL = "https://testnet.binance.vision"
# Binance WebSocket endpoints (use default port 443, not 9443)
BINANCE_WS_URL = "wss://stream.binance.com/ws"
BINANCE_TESTNET_WS_URL = "wss://testnet.binance.vision/ws"


class BinanceRESTClient:
    """
    Async REST client for Binance public API.

    Handles:
    - Historical OHLCV data
    - Order book snapshots
    - Recent trades
    - Ticker prices
    """

    def __init__(self, testnet: bool = False):
        """
        Initialize REST client.

        Args:
            testnet: Use testnet endpoints
        """
        self.base_url = BINANCE_TESTNET_REST_URL if testnet else BINANCE_REST_URL
        self.session: Optional[aiohttp.ClientSession] = None
        self.testnet = testnet

        logger.info(f"BinanceRESTClient initialized: testnet={testnet}")

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure aiohttp session exists."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self) -> None:
        """Close HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None
    ) -> Any:
        """
        Make HTTP request.

        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters

        Returns:
            JSON response
        """
        session = await self._ensure_session()
        url = f"{self.base_url}{endpoint}"

        try:
            async with session.request(method, url, params=params) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(f"API error: {response.status} - {text}")
                    raise Exception(f"API error: {response.status}")
                return await response.json()

        except aiohttp.ClientError as e:
            logger.error(f"HTTP error: {e}")
            raise

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1m",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000
    ) -> List:
        """
        Get historical klines (candlestick data).

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            interval: Kline interval (e.g., "1m", "5m", "1h", "1d")
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            limit: Number of klines (max 1000)

        Returns:
            List of kline data
        """
        params = {
            "symbol": normalize_symbol(symbol),
            "interval": interval,
            "limit": min(limit, 1000)
        }

        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        return await self._request("GET", "/api/v3/klines", params)

    async def get_order_book(
        self,
        symbol: str,
        limit: int = 100
    ) -> Dict:
        """
        Get order book snapshot.

        Args:
            symbol: Trading symbol
            limit: Depth limit (5, 10, 20, 50, 100, 500, 1000, 5000)

        Returns:
            Order book data with 'bids' and 'asks'
        """
        valid_limits = [5, 10, 20, 50, 100, 500, 1000, 5000]
        if limit not in valid_limits:
            limit = min(valid_limits, key=lambda x: abs(x - limit))

        params = {
            "symbol": normalize_symbol(symbol),
            "limit": limit
        }

        return await self._request("GET", "/api/v3/depth", params)

    async def get_recent_trades(
        self,
        symbol: str,
        limit: int = 500
    ) -> List:
        """
        Get recent trades.

        Args:
            symbol: Trading symbol
            limit: Number of trades (max 1000)

        Returns:
            List of recent trades
        """
        params = {
            "symbol": normalize_symbol(symbol),
            "limit": min(limit, 1000)
        }

        return await self._request("GET", "/api/v3/trades", params)

    async def get_ticker_price(self, symbol: str) -> Optional[float]:
        """
        Get current ticker price.

        Args:
            symbol: Trading symbol

        Returns:
            Current price
        """
        params = {"symbol": normalize_symbol(symbol)}
        data = await self._request("GET", "/api/v3/ticker/price", params)
        return float(data.get("price", 0))

    async def get_24hr_ticker(self, symbol: str) -> Dict:
        """
        Get 24hr ticker statistics.

        Args:
            symbol: Trading symbol

        Returns:
            24hr statistics
        """
        params = {"symbol": normalize_symbol(symbol)}
        return await self._request("GET", "/api/v3/ticker/24hr", params)


class WebSocketManager:
    """
    WebSocket manager for real-time Binance streams.

    Handles:
    - Kline streams
    - Order book streams
    - Trade streams
    - Connection management
    - Automatic reconnection
    """

    def __init__(self, testnet: bool = False):
        """
        Initialize WebSocket manager.

        Args:
            testnet: Use testnet endpoints
        """
        self.base_url = BINANCE_TESTNET_WS_URL if testnet else BINANCE_WS_URL
        self.testnet = testnet

        self._connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running: Set[str] = set()

        logger.info(f"WebSocketManager initialized: testnet={testnet}")

    def is_connected(self) -> bool:
        """Check if any WebSocket is connected."""
        # Check both running set and actual connections
        has_running = len(self._running) > 0
        has_connections = len(self._connections) > 0
        return has_running or has_connections

    def get_connected_streams(self) -> List[str]:
        """Get list of connected stream names."""
        # Return streams that are both in _running and have active connections
        connected = []
        for stream_name in self._running:
            if stream_name in self._connections:
                try:
                    # Check if connection is still alive
                    ws = self._connections[stream_name]
                    if ws and not ws.closed:
                        connected.append(stream_name)
                except Exception:
                    # Connection might be invalid, skip it
                    pass
        return connected

    async def _connect_stream(
        self,
        stream_name: str,
        callback: Callable
    ) -> None:
        """
        Connect to a WebSocket stream.

        Args:
            stream_name: Stream identifier
            callback: Async callback for messages
        """
        url = f"{self.base_url}/{stream_name}"
        self._callbacks[stream_name] = callback

        while stream_name in self._running:
            try:
                logger.info(f"Connecting to WebSocket stream: {stream_name}")

                async with websockets.connect(
                    url,
                    ping_interval=20,  # Send ping every 20 seconds
                    ping_timeout=10,    # Wait 10 seconds for pong
                    close_timeout=10    # Wait 10 seconds for close
                ) as ws:
                    self._connections[stream_name] = ws
                    logger.info(f"✅ WebSocket connected: {stream_name}")

                    # Notify callback of connection
                    try:
                        await callback({'type': 'connection_established', 'stream': stream_name})
                    except Exception as e:
                        logger.debug(f"Callback error on connection: {e}")

                    # Listen for messages
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            await callback(data)
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON decode error: {e}")
                        except Exception as e:
                            logger.error(f"Callback error: {e}")

            except ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {stream_name} - {e}")
                if stream_name in self._running:
                    logger.info(f"Reconnecting in 5 seconds: {stream_name}")
                    await asyncio.sleep(5)

            except Exception as e:
                error_msg = str(e)
                # Check for HTTP 404 errors (invalid stream)
                if "404" in error_msg or "HTTP" in error_msg:
                    logger.warning(f"WebSocket stream not found (404): {stream_name} - This symbol may not exist or be delisted")
                    # Remove from running set to prevent retry loops
                    if stream_name in self._running:
                        self._running.remove(stream_name)
                    # Clean up
                    if stream_name in self._connections:
                        del self._connections[stream_name]
                    if stream_name in self._tasks:
                        self._tasks[stream_name].cancel()
                        del self._tasks[stream_name]
                    if stream_name in self._callbacks:
                        del self._callbacks[stream_name]
                    return  # Exit the connection loop for this stream
                else:
                    logger.error(f"WebSocket error: {stream_name} - {e}")
                    if stream_name in self._running:
                        await asyncio.sleep(5)

        # Cleanup
        if stream_name in self._connections:
            del self._connections[stream_name]

    async def connect_kline_stream(
        self,
        symbol: str,
        interval: str = "1m",
        callback: Optional[Callable] = None
    ) -> None:
        """
        Connect to kline stream.

        Args:
            symbol: Trading symbol
            interval: Kline interval
            callback: Async callback for kline updates
        """
        stream_name = f"{symbol.lower()}@kline_{interval}"

        if stream_name in self._running:
            logger.warning(f"Stream already running: {stream_name}")
            return

        if callback is None:
            async def default_callback(data):
                pass
            callback = default_callback

        self._running.add(stream_name)
        task = asyncio.create_task(self._connect_stream(stream_name, callback))
        self._tasks[stream_name] = task

    async def connect_orderbook_stream(
        self,
        symbol: str,
        callback: Optional[Callable] = None,
        update_speed: str = "100ms"
    ) -> None:
        """
        Connect to order book stream.

        Args:
            symbol: Trading symbol
            callback: Async callback for order book updates
            update_speed: Update speed ("100ms" or "1000ms")
        """
        if update_speed == "100ms":
            stream_name = f"{symbol.lower()}@depth@100ms"
        else:
            stream_name = f"{symbol.lower()}@depth"

        if stream_name in self._running:
            logger.warning(f"Stream already running: {stream_name}")
            return

        if callback is None:
            async def default_callback(data):
                pass
            callback = default_callback

        self._running.add(stream_name)
        task = asyncio.create_task(self._connect_stream(stream_name, callback))
        self._tasks[stream_name] = task

    async def connect_trade_stream(
        self,
        symbol: str,
        callback: Optional[Callable] = None
    ) -> None:
        """
        Connect to trade stream.

        Args:
            symbol: Trading symbol
            callback: Async callback for trade updates
        """
        stream_name = f"{symbol.lower()}@trade"

        if stream_name in self._running:
            logger.warning(f"Stream already running: {stream_name}")
            return

        if callback is None:
            async def default_callback(data):
                pass
            callback = default_callback

        self._running.add(stream_name)
        task = asyncio.create_task(self._connect_stream(stream_name, callback))
        self._tasks[stream_name] = task

    async def disconnect_stream(self, stream_name: str) -> None:
        """
        Disconnect a specific stream.

        Args:
            stream_name: Stream identifier
        """
        if stream_name in self._running:
            self._running.remove(stream_name)

        if stream_name in self._connections:
            try:
                await self._connections[stream_name].close()
            except Exception:
                pass
            del self._connections[stream_name]

        if stream_name in self._tasks:
            task = self._tasks[stream_name]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._tasks[stream_name]

        if stream_name in self._callbacks:
            del self._callbacks[stream_name]

        logger.info(f"Disconnected stream: {stream_name}")

    async def disconnect_all(self) -> None:
        """Disconnect all streams."""
        stream_names = list(self._running)
        for stream_name in stream_names:
            await self.disconnect_stream(stream_name)
        logger.info("All WebSocket streams disconnected")


class MarketDataManager:
    """
    Unified market data manager.

    Provides a single interface for:
    - Historical data (REST)
    - Real-time data (WebSocket)
    - Data caching
    """

    def __init__(self, testnet: bool = False):
        """
        Initialize market data manager.

        Args:
            testnet: Use testnet endpoints
        """
        self.testnet = testnet
        self.rest_client = BinanceRESTClient(testnet=testnet)
        self.ws_manager = WebSocketManager(testnet=testnet)

        # Data cache
        self._price_cache: Dict[str, float] = {}
        self._orderbook_cache: Dict[str, Dict] = {}
        self._ohlcv_cache: Dict[str, pd.DataFrame] = {}

        logger.info(f"MarketDataManager initialized: testnet={testnet}")

    async def close(self) -> None:
        """Close all connections."""
        await self.ws_manager.disconnect_all()
        await self.rest_client.close()
        logger.info("MarketDataManager closed")

    async def get_historical_ohlcv(
        self,
        symbol: str,
        interval: str = "1m",
        hours: int = 24,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Get historical OHLCV data.

        Args:
            symbol: Trading symbol
            interval: Candle interval
            hours: Number of hours of data
            use_cache: Use cached data if available

        Returns:
            DataFrame with OHLCV data
        """
        symbol = normalize_symbol(symbol)
        cache_key = f"{symbol}_{interval}_{hours}"

        # Check cache
        if use_cache and cache_key in self._ohlcv_cache:
            cached_df = self._ohlcv_cache[cache_key]
            # Cache valid for 1 minute
            if not cached_df.empty:
                last_ts = cached_df['timestamp'].max()
                if isinstance(last_ts, pd.Timestamp):
                    last_ts = last_ts.to_pydatetime()
                if last_ts.tzinfo is None:
                    last_ts = last_ts.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - last_ts).total_seconds() < 60:
                    return cached_df

        # Calculate time range
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp() * 1000)

        # Fetch data
        try:
            # May need multiple requests for large time ranges
            all_klines = []
            current_start = start_time

            while current_start < end_time:
                klines = await self.rest_client.get_klines(
                    symbol=symbol,
                    interval=interval,
                    start_time=current_start,
                    end_time=end_time,
                    limit=1000
                )

                if not klines:
                    break

                all_klines.extend(klines)

                # Move start time to after last kline
                last_kline_time = klines[-1][0]
                if last_kline_time <= current_start:
                    break
                current_start = last_kline_time + 1

                # Avoid rate limits
                await asyncio.sleep(0.1)

            if not all_klines:
                logger.warning(f"No OHLCV data returned for {symbol}")
                return pd.DataFrame()

            # Normalize data
            df = normalize_ohlcv_data(all_klines, symbol)

            # Cache result
            self._ohlcv_cache[cache_key] = df

            return df

        except Exception as e:
            logger.error(f"Error fetching OHLCV data: {e}")
            return pd.DataFrame()

    async def get_order_book_snapshot(
        self,
        symbol: str,
        limit: int = 100
    ) -> Dict:
        """
        Get order book snapshot.

        Args:
            symbol: Trading symbol
            limit: Depth limit

        Returns:
            Order book data
        """
        symbol = normalize_symbol(symbol)

        try:
            data = await self.rest_client.get_order_book(symbol, limit)
            data['timestamp'] = int(datetime.now(timezone.utc).timestamp() * 1000)

            # Cache
            self._orderbook_cache[symbol] = data

            return data

        except Exception as e:
            logger.error(f"Error fetching order book: {e}")
            return {'bids': [], 'asks': [], 'timestamp': 0}

    async def get_recent_trades(
        self,
        symbol: str,
        limit: int = 500
    ) -> List:
        """
        Get recent trades.

        Args:
            symbol: Trading symbol
            limit: Number of trades

        Returns:
            List of trades
        """
        symbol = normalize_symbol(symbol)

        try:
            return await self.rest_client.get_recent_trades(symbol, limit)
        except Exception as e:
            logger.error(f"Error fetching recent trades: {e}")
            return []

    async def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current price.

        Args:
            symbol: Trading symbol

        Returns:
            Current price
        """
        symbol = normalize_symbol(symbol)

        try:
            price = await self.rest_client.get_ticker_price(symbol)
            self._price_cache[symbol] = price
            return price
        except Exception as e:
            logger.error(f"Error fetching price: {e}")
            # Return cached price if available
            return self._price_cache.get(symbol)

    def get_cached_price(self, symbol: str) -> Optional[float]:
        """
        Get cached price (no API call).

        Args:
            symbol: Trading symbol

        Returns:
            Cached price or None
        """
        return self._price_cache.get(normalize_symbol(symbol))

    def get_cached_orderbook(self, symbol: str) -> Optional[Dict]:
        """
        Get cached order book (no API call).

        Args:
            symbol: Trading symbol

        Returns:
            Cached order book or None
        """
        return self._orderbook_cache.get(normalize_symbol(symbol))
