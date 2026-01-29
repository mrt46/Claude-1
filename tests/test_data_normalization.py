"""
Tests for data normalization module.
"""

from datetime import datetime, timezone

import pandas as pd
import pytest

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


class TestNormalizeTimestamp:
    """Tests for timestamp normalization."""
    
    def test_normalize_datetime_utc(self):
        """Test normalizing UTC datetime."""
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = normalize_timestamp(dt)
        assert result == dt
        assert result.tzinfo == timezone.utc
    
    def test_normalize_datetime_naive(self):
        """Test normalizing naive datetime."""
        dt = datetime(2024, 1, 1, 12, 0, 0)
        result = normalize_timestamp(dt)
        assert result.tzinfo == timezone.utc
    
    def test_normalize_timestamp_milliseconds(self):
        """Test normalizing timestamp in milliseconds."""
        ts = 1704110400000  # 2024-01-01 12:00:00 UTC in milliseconds
        result = normalize_timestamp(ts)
        assert isinstance(result, datetime)
        assert result.tzinfo == timezone.utc
    
    def test_normalize_timestamp_seconds(self):
        """Test normalizing timestamp in seconds."""
        ts = 1704110400.0  # 2024-01-01 12:00:00 UTC in seconds
        result = normalize_timestamp(ts)
        assert isinstance(result, datetime)
        assert result.tzinfo == timezone.utc
    
    def test_normalize_timestamp_invalid(self):
        """Test invalid timestamp format."""
        with pytest.raises(ValueError):
            normalize_timestamp("invalid")


class TestNormalizePrice:
    """Tests for price normalization."""
    
    def test_normalize_price_float(self):
        """Test normalizing float price."""
        result = normalize_price(42000.123456789, precision=8)
        assert float(result) == 42000.12345679  # Rounded to 8 decimals
    
    def test_normalize_price_string(self):
        """Test normalizing string price."""
        result = normalize_price("42000.50", precision=2)
        assert float(result) == 42000.50
    
    def test_normalize_price_decimal(self):
        """Test normalizing Decimal price."""
        from decimal import Decimal
        result = normalize_price(Decimal("42000.123456789"), precision=8)
        assert float(result) == 42000.12345679


class TestNormalizeSymbol:
    """Tests for symbol normalization."""
    
    def test_normalize_symbol_binance_format(self):
        """Test normalizing Binance format symbol."""
        assert normalize_symbol("BTCUSDT") == "BTCUSDT"
    
    def test_normalize_symbol_with_separator(self):
        """Test normalizing symbol with separator."""
        assert normalize_symbol("BTC/USDT") == "BTCUSDT"
        assert normalize_symbol("BTC-USDT") == "BTCUSDT"
        assert normalize_symbol("BTC_USDT") == "BTCUSDT"
    
    def test_normalize_symbol_lowercase(self):
        """Test normalizing lowercase symbol."""
        assert normalize_symbol("btcusdt") == "BTCUSDT"


class TestNormalizeOHLCV:
    """Tests for OHLCV data normalization."""
    
    def test_normalize_ohlcv_list_format(self):
        """Test normalizing OHLCV in list format."""
        data = [
            [1704110400000, "42000", "42100", "41900", "42050", "100.5", 1704110459999, "200.5", 100, "50.5", "51.5", "0"]
        ]
        result = normalize_ohlcv_data(data, "BTCUSDT")
        assert len(result) == 1
        assert result.iloc[0]['open'] == 42000.0
        assert result.iloc[0]['high'] == 42100.0
        assert result.iloc[0]['low'] == 41900.0
        assert result.iloc[0]['close'] == 42050.0
        assert result.iloc[0]['volume'] == 100.5
    
    def test_normalize_ohlcv_dict_format(self):
        """Test normalizing OHLCV in dict format."""
        data = [
            {
                'timestamp': 1704110400000,
                'open': '42000',
                'high': '42100',
                'low': '41900',
                'close': '42050',
                'volume': '100.5',
                'trades': 100
            }
        ]
        result = normalize_ohlcv_data(data, "BTCUSDT")
        assert len(result) == 1
        assert result.iloc[0]['open'] == 42000.0
    
    def test_normalize_ohlcv_empty(self):
        """Test normalizing empty OHLCV data."""
        with pytest.raises(ValueError, match="Empty OHLCV data"):
            normalize_ohlcv_data([], "BTCUSDT")
    
    def test_normalize_ohlcv_invalid_ohlc(self):
        """Test invalid OHLC data."""
        data = [
            [1704110400000, "42000", "41900", "42100", "42050", "100.5", 1704110459999, "200.5", 100, "50.5", "51.5", "0"]
        ]
        with pytest.raises(ValueError, match="Invalid OHLC"):
            normalize_ohlcv_data(data, "BTCUSDT")


class TestNormalizeOrderBook:
    """Tests for order book normalization."""
    
    def test_normalize_orderbook(self):
        """Test normalizing order book data."""
        data = {
            'bids': [['42000', '1.5'], ['41999', '2.0']],
            'asks': [['42001', '1.3'], ['42002', '1.7']],
            'timestamp': 1704110400000
        }
        result = normalize_orderbook_data(data, "BTCUSDT")
        assert result['symbol'] == "BTCUSDT"
        assert len(result['bids']) == 2
        assert len(result['asks']) == 2
        assert result['bids'][0][0] == 42000.0
        assert result['bids'][0][1] == 1.5


class TestNormalizeTradeData:
    """Tests for trade data normalization."""
    
    def test_normalize_trade_data(self):
        """Test normalizing trade data."""
        data = [
            {
                'timestamp': 1704110400000,
                'price': '42000',
                'quantity': '0.5',
                'isBuyerMaker': True
            }
        ]
        result = normalize_trade_data(data, "BTCUSDT")
        assert len(result) == 1
        assert result.iloc[0]['price'] == 42000.0
        assert result.iloc[0]['quantity'] == 0.5
        assert result.iloc[0]['is_buyer_maker'] == True


class TestFillMissingData:
    """Tests for filling missing data."""
    
    def test_fill_missing_ffill(self):
        """Test forward fill."""
        df = pd.DataFrame({
            'price': [100.0, None, None, 103.0],
            'volume': [10.0, None, 12.0, None]
        })
        result = fill_missing_data(df, method='ffill')
        assert result['price'].iloc[1] == 100.0
        assert result['price'].iloc[2] == 100.0
    
    def test_fill_missing_interpolate(self):
        """Test interpolation."""
        df = pd.DataFrame({
            'price': [100.0, None, None, 103.0],
        })
        result = fill_missing_data(df, method='interpolate')
        assert not result['price'].isna().any()
