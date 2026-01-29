"""
Pytest configuration and fixtures.
"""

import asyncio
from datetime import datetime, timezone
from typing import Generator

import numpy as np
import pandas as pd
import pytest

from src.analysis.orderbook import OrderBook


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_ohlcv_df() -> pd.DataFrame:
    """Create sample OHLCV DataFrame."""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1h', tz=timezone.utc)
    
    # Generate realistic price data
    np.random.seed(42)
    base_price = 42000.0
    prices = []
    volumes = []
    
    for i in range(100):
        change = np.random.normal(0, 0.01)  # 1% volatility
        price = base_price * (1 + change)
        base_price = price
        prices.append(price)
        volumes.append(np.random.uniform(100, 1000))
    
    df = pd.DataFrame({
        'symbol': 'BTCUSDT',
        'open': [p * 0.999 for p in prices],
        'high': [p * 1.002 for p in prices],
        'low': [p * 0.998 for p in prices],
        'close': prices,
        'volume': volumes,
        'trades': np.random.randint(100, 1000, 100)
    }, index=dates)
    
    return df


@pytest.fixture
def sample_orderbook() -> OrderBook:
    """Create sample order book."""
    bids = [
        (42000.0, 1.5),
        (41999.0, 2.0),
        (41998.0, 1.8),
        (41997.0, 2.5),
        (41996.0, 1.2),
    ]
    
    asks = [
        (42001.0, 1.3),
        (42002.0, 1.7),
        (42003.0, 2.1),
        (42004.0, 1.9),
        (42005.0, 2.3),
    ]
    
    return OrderBook(
        symbol='BTCUSDT',
        bids=bids,
        asks=asks,
        timestamp=datetime.now(timezone.utc)
    )


@pytest.fixture
def sample_trades_df() -> pd.DataFrame:
    """Create sample trades DataFrame."""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1min', tz=timezone.utc)
    
    np.random.seed(42)
    prices = np.random.uniform(41900, 42100, 100)
    quantities = np.random.uniform(0.01, 1.0, 100)
    is_buyer_maker = np.random.choice([True, False], 100)
    
    df = pd.DataFrame({
        'price': prices,
        'quantity': quantities,
        'is_buyer_maker': is_buyer_maker
    }, index=dates)
    
    return df
