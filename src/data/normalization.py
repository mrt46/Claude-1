"""
Data normalization utilities.

Provides functions to normalize data from various exchange formats
into a consistent internal format.
"""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from src.core.logger import get_logger

logger = get_logger(__name__)


def normalize_timestamp(
    timestamp: Union[datetime, int, float, str]
) -> datetime:
    """
    Normalize timestamp to UTC datetime.

    Accepts:
    - datetime objects (with or without timezone)
    - Unix timestamps in milliseconds (int > 1e12)
    - Unix timestamps in seconds (float or int < 1e12)
    - ISO format strings

    Args:
        timestamp: Timestamp in various formats

    Returns:
        datetime object with UTC timezone

    Raises:
        ValueError: If timestamp format is invalid
    """
    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc)

    if isinstance(timestamp, (int, float)):
        # Determine if milliseconds or seconds
        if timestamp > 1e12:
            # Milliseconds
            ts_seconds = timestamp / 1000
        else:
            # Seconds
            ts_seconds = float(timestamp)

        return datetime.fromtimestamp(ts_seconds, tz=timezone.utc)

    if isinstance(timestamp, str):
        try:
            # Try ISO format
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass

        try:
            # Try parsing as numeric string
            return normalize_timestamp(float(timestamp))
        except ValueError:
            pass

    raise ValueError(f"Invalid timestamp format: {timestamp}")


def normalize_price(
    price: Union[float, str, Decimal],
    precision: int = 8
) -> Decimal:
    """
    Normalize price to Decimal with specified precision.

    Args:
        price: Price value in various formats
        precision: Number of decimal places (default: 8)

    Returns:
        Decimal with specified precision
    """
    if isinstance(price, str):
        dec = Decimal(price)
    elif isinstance(price, Decimal):
        dec = price
    else:
        dec = Decimal(str(price))

    # Round to precision
    quantize_str = '0.' + '0' * precision
    return dec.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)


def normalize_quantity(
    quantity: Union[float, str, Decimal],
    precision: int = 8
) -> Decimal:
    """
    Normalize quantity to Decimal with specified precision.

    Args:
        quantity: Quantity value in various formats
        precision: Number of decimal places (default: 8)

    Returns:
        Decimal with specified precision
    """
    return normalize_price(quantity, precision)


def normalize_symbol(symbol: str) -> str:
    """
    Normalize trading symbol to Binance format.

    Removes separators and converts to uppercase.

    Examples:
        "BTC/USDT" -> "BTCUSDT"
        "btc-usdt" -> "BTCUSDT"
        "BTC_USDT" -> "BTCUSDT"

    Args:
        symbol: Symbol in various formats

    Returns:
        Symbol in Binance format (e.g., "BTCUSDT")
    """
    # Remove common separators
    normalized = symbol.replace('/', '').replace('-', '').replace('_', '')
    # Convert to uppercase
    return normalized.upper()


def normalize_ohlcv_data(
    data: List[Union[List, Dict]],
    symbol: str
) -> pd.DataFrame:
    """
    Normalize OHLCV data to pandas DataFrame.

    Accepts Binance kline format (list of lists) or dict format.

    Binance kline format:
    [
        open_time, open, high, low, close, volume,
        close_time, quote_volume, trades, taker_buy_base,
        taker_buy_quote, ignore
    ]

    Args:
        data: OHLCV data in list or dict format
        symbol: Trading symbol

    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume, symbol

    Raises:
        ValueError: If data is empty or invalid
    """
    if not data:
        raise ValueError("Empty OHLCV data")

    rows = []

    for item in data:
        if isinstance(item, list):
            # Binance kline format
            if len(item) < 6:
                logger.warning(f"Invalid kline data: {item}")
                continue

            timestamp = normalize_timestamp(item[0])
            open_price = float(item[1])
            high_price = float(item[2])
            low_price = float(item[3])
            close_price = float(item[4])
            volume = float(item[5])
            trades = int(item[8]) if len(item) > 8 else 0

        elif isinstance(item, dict):
            # Dict format
            ts = item.get('timestamp') or item.get('open_time') or item.get('t')
            timestamp = normalize_timestamp(ts)

            open_price = float(item.get('open') or item.get('o', 0))
            high_price = float(item.get('high') or item.get('h', 0))
            low_price = float(item.get('low') or item.get('l', 0))
            close_price = float(item.get('close') or item.get('c', 0))
            volume = float(item.get('volume') or item.get('v', 0))
            trades = int(item.get('trades') or item.get('n', 0))
        else:
            logger.warning(f"Unknown OHLCV format: {type(item)}")
            continue

        # Validate OHLC consistency
        if high_price < low_price:
            raise ValueError(
                f"Invalid OHLC data: high ({high_price}) < low ({low_price})"
            )
        if high_price < open_price or high_price < close_price:
            raise ValueError(
                f"Invalid OHLC data: high ({high_price}) < open ({open_price}) or close ({close_price})"
            )
        if low_price > open_price or low_price > close_price:
            raise ValueError(
                f"Invalid OHLC data: low ({low_price}) > open ({open_price}) or close ({close_price})"
            )

        rows.append({
            'timestamp': timestamp,
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume,
            'trades': trades,
            'symbol': normalize_symbol(symbol)
        })

    if not rows:
        raise ValueError("No valid OHLCV data after normalization")

    df = pd.DataFrame(rows)
    df = df.sort_values('timestamp').reset_index(drop=True)

    return df


def normalize_orderbook_data(
    data: Dict[str, Any],
    symbol: str
) -> Dict[str, Any]:
    """
    Normalize order book data.

    Converts string prices/quantities to floats and adds metadata.

    Args:
        data: Order book data with 'bids' and 'asks' keys
        symbol: Trading symbol

    Returns:
        Normalized order book dictionary:
        {
            'symbol': str,
            'timestamp': datetime,
            'bids': List[Tuple[float, float]],  # (price, quantity)
            'asks': List[Tuple[float, float]]   # (price, quantity)
        }
    """
    timestamp = data.get('timestamp') or data.get('T') or data.get('E')
    if timestamp:
        normalized_ts = normalize_timestamp(timestamp)
    else:
        normalized_ts = datetime.now(timezone.utc)

    def convert_levels(levels: List) -> List[tuple]:
        """Convert price/quantity strings to floats."""
        result = []
        for level in levels:
            if isinstance(level, (list, tuple)):
                price = float(level[0])
                quantity = float(level[1])
            elif isinstance(level, dict):
                price = float(level.get('price') or level.get('p', 0))
                quantity = float(level.get('quantity') or level.get('q', 0))
            else:
                continue
            result.append((price, quantity))
        return result

    bids = convert_levels(data.get('bids', []))
    asks = convert_levels(data.get('asks', []))

    return {
        'symbol': normalize_symbol(symbol),
        'timestamp': normalized_ts,
        'bids': bids,
        'asks': asks
    }


def normalize_trade_data(
    data: List[Dict],
    symbol: str
) -> pd.DataFrame:
    """
    Normalize trade data to pandas DataFrame.

    Args:
        data: List of trade records
        symbol: Trading symbol

    Returns:
        DataFrame with columns: timestamp, price, quantity, is_buyer_maker, symbol
    """
    if not data:
        return pd.DataFrame(columns=['timestamp', 'price', 'quantity', 'is_buyer_maker', 'symbol'])

    rows = []

    for trade in data:
        ts = trade.get('timestamp') or trade.get('T') or trade.get('time')
        timestamp = normalize_timestamp(ts)

        price = float(trade.get('price') or trade.get('p', 0))
        quantity = float(trade.get('quantity') or trade.get('q') or trade.get('qty', 0))

        # Determine if buyer is maker
        is_buyer_maker = trade.get('isBuyerMaker') or trade.get('m', False)
        if isinstance(is_buyer_maker, str):
            is_buyer_maker = is_buyer_maker.lower() == 'true'

        rows.append({
            'timestamp': timestamp,
            'price': price,
            'quantity': quantity,
            'is_buyer_maker': bool(is_buyer_maker),
            'symbol': normalize_symbol(symbol)
        })

    df = pd.DataFrame(rows)
    df = df.sort_values('timestamp').reset_index(drop=True)

    return df


def fill_missing_data(
    df: pd.DataFrame,
    method: str = 'ffill',
    columns: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    Fill missing data in DataFrame.

    Args:
        df: DataFrame with potential missing values
        method: Fill method ('ffill', 'bfill', 'interpolate')
        columns: Specific columns to fill (default: all numeric columns)

    Returns:
        DataFrame with filled values
    """
    df = df.copy()

    if columns is None:
        columns = df.select_dtypes(include=['float64', 'int64']).columns.tolist()

    for col in columns:
        if col not in df.columns:
            continue

        if method == 'ffill':
            df[col] = df[col].ffill()
        elif method == 'bfill':
            df[col] = df[col].bfill()
        elif method == 'interpolate':
            df[col] = df[col].interpolate(method='linear')
        else:
            raise ValueError(f"Unknown fill method: {method}")

    return df
