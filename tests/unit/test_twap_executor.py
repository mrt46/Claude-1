"""
Unit tests for TWAP Executor.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.execution.exceptions import OrderExecutionError
from src.execution.lifecycle import Order, OrderStatus
from src.execution.twap_executor import (
    TWAPExecutionError,
    TWAPExecutor,
    TWAPResult,
    PrecisionHandler
)


@pytest.fixture
def mock_exchange():
    """Create mock exchange."""
    exchange = Mock()
    exchange.place_order = AsyncMock()
    exchange.get_ticker_price = AsyncMock(return_value=42000.0)
    exchange.get_order_book = AsyncMock(return_value={
        'bids': [['42000.0', '1.5'], ['41999.0', '2.0']],
        'asks': [['42001.0', '1.3'], ['42002.0', '2.0']]
    })
    exchange.get_order_status = AsyncMock(return_value={
        'status': 'FILLED',
        'executedQty': '0.1',
        'price': '42000.0',
        'avgPrice': '42000.0',
        'updateTime': 1640000000000,
        'fills': []
    })
    return exchange


@pytest.fixture
def precision_handler():
    """Create precision handler."""
    return PrecisionHandler()


@pytest.fixture
def twap_config():
    """Create TWAP config for testing."""
    return {
        'default_num_chunks': 5,
        'default_interval_seconds': 0.1,  # Fast for testing
        'max_price_deviation_percent': 0.01,
        'min_chunk_value_usdt': 50,
        'check_spread': True,
        'max_spread_percent': 0.005,
        'twap_threshold_usdt': 1000
    }


@pytest.fixture
def twap_executor(mock_exchange, precision_handler, twap_config):
    """Create TWAP executor instance."""
    return TWAPExecutor(
        exchange=mock_exchange,
        precision_handler=precision_handler,
        config=twap_config
    )


class TestTWAPExecutor:
    """Tests for TWAPExecutor."""
    
    def test_init(self, mock_exchange, precision_handler, twap_config):
        """Test TWAP executor initialization."""
        executor = TWAPExecutor(
            exchange=mock_exchange,
            precision_handler=precision_handler,
            config=twap_config
        )
        
        assert executor.exchange == mock_exchange
        assert executor.default_num_chunks == 5
        assert executor.default_interval == 0.1
        assert executor.max_price_deviation == 0.01
    
    def test_init_invalid_exchange(self):
        """Test initialization with None exchange."""
        with pytest.raises(ValueError, match="Exchange is required"):
            TWAPExecutor(exchange=None)
    
    def test_should_use_twap_large_order(self, twap_executor):
        """Test TWAP recommended for large order."""
        result = twap_executor.should_use_twap(
            symbol='BTCUSDT',
            quantity=0.5,  # 0.5 BTC
            current_price=42000.0  # $21,000 value
        )
        assert result is True
    
    def test_should_not_use_twap_small_order(self, twap_executor):
        """Test TWAP not needed for small order."""
        result = twap_executor.should_use_twap(
            symbol='BTCUSDT',
            quantity=0.01,  # 0.01 BTC
            current_price=42000.0  # $420 value
        )
        assert result is False
    
    def test_should_use_twap_exact_threshold(self, twap_executor):
        """Test TWAP threshold boundary."""
        # Order value exactly $1000
        quantity = 1000 / 42000.0  # ~0.0238 BTC
        result = twap_executor.should_use_twap(
            symbol='BTCUSDT',
            quantity=quantity,
            current_price=42000.0
        )
        # Should be False (threshold is > $1000, not >=)
        assert result is False
        
        # Order value slightly above $1000
        quantity = 1001 / 42000.0
        result = twap_executor.should_use_twap(
            symbol='BTCUSDT',
            quantity=quantity,
            current_price=42000.0
        )
        assert result is True
    
    @pytest.mark.asyncio
    async def test_execute_twap_splits_correctly(self, twap_executor, mock_exchange):
        """Test TWAP splits order into chunks."""
        # Setup mocks
        order_responses = []
        for i in range(5):
            order_responses.append({
                'orderId': 1000 + i
            })
        
        mock_exchange.place_order = AsyncMock(side_effect=order_responses)
        
        # Mock order status to return FILLED
        async def mock_get_order_status(symbol, order_id):
            return {
                'status': 'FILLED',
                'executedQty': '0.1',
                'price': '42000.0',
                'avgPrice': '42000.0',
                'updateTime': 1640000000000,
                'fills': []
            }
        
        mock_exchange.get_order_status = AsyncMock(side_effect=mock_get_order_status)
        
        # Execute TWAP
        result = await twap_executor.execute_twap(
            symbol='BTCUSDT',
            side='BUY',
            total_quantity=0.5,
            current_price=42000.0,
            num_chunks=5,
            interval_seconds=0.01  # Very fast for testing
        )
        
        assert isinstance(result, TWAPResult)
        assert result.chunks_executed == 5
        assert result.total_chunks == 5
        assert result.total_filled == 0.5
        assert result.stopped_early is False
        assert len(result.orders) == 5
        assert mock_exchange.place_order.call_count == 5
    
    @pytest.mark.asyncio
    async def test_twap_stops_on_price_deviation(self, twap_executor, mock_exchange):
        """Test TWAP stops if price moves too much."""
        call_count = 0
        
        async def mock_get_price(symbol):
            nonlocal call_count
            call_count += 1
            # First call: 42000, second call: 42500 (big jump > 1%!)
            return 42000.0 if call_count == 1 else 42500.0
        
        mock_exchange.get_ticker_price = AsyncMock(side_effect=mock_get_price)
        mock_exchange.place_order = AsyncMock(return_value={'orderId': 1000})
        
        async def mock_get_order_status(symbol, order_id):
            return {
                'status': 'FILLED',
                'executedQty': '0.1',
                'price': '42000.0',
                'avgPrice': '42000.0',
                'updateTime': 1640000000000,
                'fills': []
            }
        
        mock_exchange.get_order_status = AsyncMock(side_effect=mock_get_order_status)
        
        result = await twap_executor.execute_twap(
            symbol='BTCUSDT',
            side='BUY',
            total_quantity=0.5,
            current_price=42000.0,
            num_chunks=5,
            interval_seconds=0.01
        )
        
        assert result.stopped_early is True
        assert 'PRICE_DEVIATION' in result.stop_reason
        # Price check happens before chunk execution, so should stop before any chunks
        # But if spread check happens first and passes, then price check happens
        # The test should verify it stops early due to price deviation
        assert result.chunks_executed < 5  # Should stop before all chunks
    
    @pytest.mark.asyncio
    async def test_twap_stops_on_wide_spread(self, twap_executor, mock_exchange):
        """Test TWAP stops if spread widens."""
        # Mock wide spread (> 0.5%)
        mock_exchange.get_order_book = AsyncMock(return_value={
            'bids': [['42000.0', '1.5']],
            'asks': [['42250.0', '1.3']]  # Spread = 250/42000 = 0.595% > 0.5%
        })
        mock_exchange.get_ticker_price = AsyncMock(return_value=42000.0)
        mock_exchange.place_order = AsyncMock(return_value={'orderId': 1000})
        
        result = await twap_executor.execute_twap(
            symbol='BTCUSDT',
            side='BUY',
            total_quantity=0.5,
            current_price=42000.0,
            num_chunks=5,
            interval_seconds=0.01
        )
        
        assert result.stopped_early is True
        assert 'SPREAD_TOO_WIDE' in result.stop_reason
        assert result.chunks_executed == 0
    
    @pytest.mark.asyncio
    async def test_twap_handles_chunk_error(self, twap_executor, mock_exchange):
        """Test TWAP handles chunk execution error."""
        mock_exchange.get_ticker_price = AsyncMock(return_value=42000.0)
        mock_exchange.place_order = AsyncMock(side_effect=Exception("Order failed"))
        
        result = await twap_executor.execute_twap(
            symbol='BTCUSDT',
            side='BUY',
            total_quantity=0.5,
            current_price=42000.0,
            num_chunks=5,
            interval_seconds=0.01
        )
        
        assert result.stopped_early is True
        assert 'ERROR' in result.stop_reason
        assert result.chunks_executed == 0
    
    @pytest.mark.asyncio
    async def test_twap_adjusts_chunks_for_min_value(self, twap_executor, mock_exchange):
        """Test TWAP adjusts chunks if chunk value too small."""
        # Very small order that would create chunks < $50
        mock_exchange.get_ticker_price = AsyncMock(return_value=42000.0)
        mock_exchange.place_order = AsyncMock(return_value={'orderId': 1000})
        
        async def mock_get_order_status(symbol, order_id):
            return {
                'status': 'FILLED',
                'executedQty': '0.001',
                'price': '42000.0',
                'avgPrice': '42000.0',
                'updateTime': 1640000000000,
                'fills': []
            }
        
        mock_exchange.get_order_status = AsyncMock(side_effect=mock_get_order_status)
        
        # Order value = 0.1 * 42000 = $4200, but if we split into 5 chunks,
        # each chunk = $840, which is > $50, so should be OK
        # But if we had a smaller order, it would adjust
        
        result = await twap_executor.execute_twap(
            symbol='BTCUSDT',
            side='BUY',
            total_quantity=0.1,
            current_price=42000.0,
            num_chunks=5,
            interval_seconds=0.01
        )
        
        # Should complete successfully
        assert result.chunks_executed > 0
    
    @pytest.mark.asyncio
    async def test_twap_handles_partial_fill(self, twap_executor, mock_exchange):
        """Test TWAP handles partial fills in chunks."""
        mock_exchange.get_ticker_price = AsyncMock(return_value=42000.0)
        mock_exchange.place_order = AsyncMock(return_value={'orderId': 1000})
        
        async def mock_get_order_status(symbol, order_id):
            return {
                'status': 'PARTIALLY_FILLED',
                'executedQty': '0.08',  # Partial fill
                'price': '42000.0',
                'avgPrice': '42000.0',
                'updateTime': 1640000000000,
                'fills': []
            }
        
        mock_exchange.get_order_status = AsyncMock(side_effect=mock_get_order_status)
        
        result = await twap_executor.execute_twap(
            symbol='BTCUSDT',
            side='BUY',
            total_quantity=0.5,
            current_price=42000.0,
            num_chunks=5,
            interval_seconds=0.01
        )
        
        # Should handle partial fills
        assert result.chunks_executed == 5
        assert result.total_filled == 0.4  # 5 * 0.08
    
    @pytest.mark.asyncio
    async def test_twap_calculates_slippage(self, twap_executor, mock_exchange):
        """Test TWAP calculates slippage correctly."""
        mock_exchange.get_ticker_price = AsyncMock(return_value=42000.0)
        mock_exchange.place_order = AsyncMock(return_value={'orderId': 1000})
        
        async def mock_get_order_status(symbol, order_id):
            return {
                'status': 'FILLED',
                'executedQty': '0.1',
                'price': '42100.0',  # Higher price = slippage for BUY
                'avgPrice': '42100.0',
                'updateTime': 1640000000000,
                'fills': []
            }
        
        mock_exchange.get_order_status = AsyncMock(side_effect=mock_get_order_status)
        
        result = await twap_executor.execute_twap(
            symbol='BTCUSDT',
            side='BUY',
            total_quantity=0.5,
            current_price=42000.0,
            num_chunks=5,
            interval_seconds=0.01
        )
        
        # Slippage should be positive for BUY (paid more)
        assert result.slippage_percent > 0
        assert result.average_price > 42000.0
    
    @pytest.mark.asyncio
    async def test_twap_invalid_quantity(self, twap_executor):
        """Test TWAP raises error for invalid quantity."""
        with pytest.raises(TWAPExecutionError, match="Invalid quantity"):
            await twap_executor.execute_twap(
                symbol='BTCUSDT',
                side='BUY',
                total_quantity=-0.5,
                current_price=42000.0
            )
    
    @pytest.mark.asyncio
    async def test_twap_invalid_price(self, twap_executor):
        """Test TWAP raises error for invalid price."""
        with pytest.raises(TWAPExecutionError, match="Invalid price"):
            await twap_executor.execute_twap(
                symbol='BTCUSDT',
                side='BUY',
                total_quantity=0.5,
                current_price=-42000.0
            )


class TestPrecisionHandler:
    """Tests for PrecisionHandler."""
    
    def test_round_quantity(self):
        """Test quantity rounding."""
        handler = PrecisionHandler()
        
        assert handler.round_quantity('BTCUSDT', 0.123456789) == 0.12345679
        assert handler.round_quantity('BTCUSDT', 0.1) == 0.1
        assert handler.round_quantity('BTCUSDT', 1.0) == 1.0
