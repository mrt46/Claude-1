"""
Data layer for the trading bot.

Provides:
- Database clients (Redis, TimescaleDB)
- Market data management (REST, WebSocket)
- Data normalization utilities
"""

from src.data.database import RedisClient, TimescaleDBClient
from src.data.market_data import MarketDataManager, WebSocketManager
from src.data.normalization import (
    fill_missing_data,
    normalize_ohlcv_data,
    normalize_orderbook_data,
    normalize_price,
    normalize_quantity,
    normalize_symbol,
    normalize_timestamp,
    normalize_trade_data,
)

__all__ = [
    # Database
    "RedisClient",
    "TimescaleDBClient",
    # Market Data
    "MarketDataManager",
    "WebSocketManager",
    # Normalization
    "normalize_timestamp",
    "normalize_price",
    "normalize_quantity",
    "normalize_symbol",
    "normalize_ohlcv_data",
    "normalize_orderbook_data",
    "normalize_trade_data",
    "fill_missing_data",
]
