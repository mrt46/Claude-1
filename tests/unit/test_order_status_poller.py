"""
Unit tests for Order Status Poller.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.execution.exceptions import OrderStatusError
from src.execution.lifecycle import Order, OrderStatus
from src.execution.order_status_poller import OrderFillResult, OrderStatusPoller


@pytest.fixture
def mock_exchange():
    """Create mock exchange."""
    exchange = Mock()
    exchange.get_order_status = AsyncMock()
    return exchange


@pytest.fixture
def order_status_poller(mock_exchange):
    """Create order status poller instance."""
    return OrderStatusPoller(
        exchange=mock_exchange,
        poll_interval_seconds=0.1,  # Fast for testing
        default_timeout_seconds=1  # Short timeout for testing
    )


@pytest.fixture
def sample_order():
    """Create sample order."""
    return Order(
        id='test_order_1',
        symbol='BTCUSDT',
        side='BUY',
        order_type='market',
        quantity=0.1,
        price=None,
        status=OrderStatus.SUBMITTED,
        exchange_order_id='12345'
    )


class TestOrderStatusPoller:
    """Tests for OrderStatusPoller."""
    
    def test_init(self, mock_exchange):
        """Test poller initialization."""
        poller = OrderStatusPoller(
            exchange=mock_exchange,
            poll_interval_seconds=2.0,
            default_timeout_seconds=30
        )
        
        assert poller.exchange == mock_exchange
        assert poller.poll_interval == 2.0
        assert poller.default_timeout == 30
    
    def test_init_invalid_exchange(self):
        """Test initialization with None exchange."""
        with pytest.raises(ValueError, match="Exchange is required"):
            OrderStatusPoller(exchange=None)
    
    def test_init_invalid_interval(self):
        """Test initialization with invalid interval."""
        exchange = Mock()
        with pytest.raises(ValueError, match="poll_interval_seconds must be positive"):
            OrderStatusPoller(exchange=exchange, poll_interval_seconds=-1)
    
    def test_init_invalid_timeout(self):
        """Test initialization with invalid timeout."""
        exchange = Mock()
        with pytest.raises(ValueError, match="default_timeout_seconds must be positive"):
            OrderStatusPoller(exchange=exchange, default_timeout_seconds=-1)
    
    @pytest.mark.asyncio
    async def test_wait_for_fill_filled(self, order_status_poller, sample_order, mock_exchange):
        """Test waiting for filled order."""
        mock_exchange.get_order_status = AsyncMock(return_value={
            'status': 'FILLED',
            'executedQty': '0.1',
            'price': '42000.0',
            'avgPrice': '42000.0',
            'updateTime': 1640000000000,
            'fills': [
                {
                    'price': '42000.0',
                    'qty': '0.1',
                    'commission': '0.042',
                    'commissionAsset': 'USDT'
                }
            ]
        })
        
        result = await order_status_poller.wait_for_fill(sample_order, timeout=1)
        
        assert isinstance(result, OrderFillResult)
        assert result.status == 'FILLED'
        assert result.filled_quantity == 0.1
        assert result.avg_fill_price == 42000.0
        assert result.fees > 0
        assert result.polls_count > 0
    
    @pytest.mark.asyncio
    async def test_wait_for_fill_partial(self, order_status_poller, sample_order, mock_exchange):
        """Test detecting partial fill."""
        mock_exchange.get_order_status = AsyncMock(return_value={
            'status': 'PARTIALLY_FILLED',
            'executedQty': '0.05',
            'price': '42000.0',
            'avgPrice': '42000.0',
            'updateTime': 1640000000000,
            'fills': [
                {
                    'price': '42000.0',
                    'qty': '0.05',
                    'commission': '0.021',
                    'commissionAsset': 'USDT'
                }
            ]
        })
        
        result = await order_status_poller.wait_for_fill(sample_order, timeout=1)
        
        assert result.status == 'PARTIAL'
        assert result.filled_quantity == 0.05
        assert result.avg_fill_price == 42000.0
    
    @pytest.mark.asyncio
    async def test_wait_for_fill_timeout(self, order_status_poller, sample_order, mock_exchange):
        """Test timeout handling."""
        # Mock order status to always return NEW (pending)
        mock_exchange.get_order_status = AsyncMock(return_value={
            'status': 'NEW',
            'executedQty': '0',
            'updateTime': 1640000000000
        })
        
        result = await order_status_poller.wait_for_fill(sample_order, timeout=0.2)
        
        assert result.status == 'TIMEOUT'
        assert result.polls_count > 0
    
    @pytest.mark.asyncio
    async def test_wait_for_fill_canceled(self, order_status_poller, sample_order, mock_exchange):
        """Test handling canceled order."""
        mock_exchange.get_order_status = AsyncMock(return_value={
            'status': 'CANCELED',
            'executedQty': '0',
            'updateTime': 1640000000000
        })
        
        result = await order_status_poller.wait_for_fill(sample_order, timeout=1)
        
        assert result.status == 'FAILED'
        assert result.failure_reason == 'CANCELED'
        assert result.filled_quantity == 0
    
    @pytest.mark.asyncio
    async def test_wait_for_fill_rejected(self, order_status_poller, sample_order, mock_exchange):
        """Test handling rejected order."""
        mock_exchange.get_order_status = AsyncMock(return_value={
            'status': 'REJECTED',
            'executedQty': '0',
            'updateTime': 1640000000000
        })
        
        result = await order_status_poller.wait_for_fill(sample_order, timeout=1)
        
        assert result.status == 'FAILED'
        assert result.failure_reason == 'REJECTED'
    
    @pytest.mark.asyncio
    async def test_wait_for_fill_invalid_order(self, order_status_poller):
        """Test handling invalid order."""
        # Order without exchange_order_id
        invalid_order = Order(
            id='test',
            symbol='BTCUSDT',
            side='BUY',
            order_type='market',
            quantity=0.1,
            price=None,
            status=OrderStatus.PENDING,
            exchange_order_id=None
        )
        
        with pytest.raises(ValueError, match="Order must have exchange_order_id"):
            await order_status_poller.wait_for_fill(invalid_order)
    
    @pytest.mark.asyncio
    async def test_wait_for_fill_string_order_id(self, order_status_poller, mock_exchange):
        """Test handling string order ID."""
        order = Order(
            id='test',
            symbol='BTCUSDT',
            side='BUY',
            order_type='market',
            quantity=0.1,
            price=None,
            status=OrderStatus.SUBMITTED,
            exchange_order_id='12345'  # String
        )
        
        mock_exchange.get_order_status = AsyncMock(return_value={
            'status': 'FILLED',
            'executedQty': '0.1',
            'price': '42000.0',
            'avgPrice': '42000.0',
            'updateTime': 1640000000000,
            'fills': []
        })
        
        result = await order_status_poller.wait_for_fill(order, timeout=1)
        
        assert result.status == 'FILLED'
        # Should convert string to int
        # Check that it was called with keyword arguments
        mock_exchange.get_order_status.assert_called()
        call_args = mock_exchange.get_order_status.call_args
        assert call_args.kwargs['symbol'] == 'BTCUSDT'
        assert call_args.kwargs['order_id'] == 12345
    
    @pytest.mark.asyncio
    async def test_calculate_fees_usdt(self, order_status_poller, mock_exchange):
        """Test fee calculation with USDT commission."""
        status_data = {
            'fills': [
                {
                    'price': '42000.0',
                    'qty': '0.1',
                    'commission': '0.042',
                    'commissionAsset': 'USDT'
                },
                {
                    'price': '42001.0',
                    'qty': '0.05',
                    'commission': '0.021',
                    'commissionAsset': 'USDT'
                }
            ]
        }
        
        fees = order_status_poller._calculate_fees(status_data)
        
        assert fees == 0.063  # 0.042 + 0.021
    
    @pytest.mark.asyncio
    async def test_calculate_fees_bnb(self, order_status_poller, mock_exchange):
        """Test fee calculation with BNB commission."""
        status_data = {
            'fills': [
                {
                    'price': '42000.0',
                    'qty': '0.1',
                    'commission': '0.001',
                    'commissionAsset': 'BNB'
                }
            ]
        }
        
        fees = order_status_poller._calculate_fees(status_data)
        
        # Should convert BNB to USDT (using placeholder price)
        assert fees > 0
    
    @pytest.mark.asyncio
    async def test_calculate_fees_no_fills(self, order_status_poller, mock_exchange):
        """Test fee calculation without fills array."""
        status_data = {
            'executedQty': '0.1',
            'avgPrice': '42000.0'
        }
        
        fees = order_status_poller._calculate_fees(status_data)
        
        # Should estimate (0.1% of fill value)
        fill_value = 0.1 * 42000.0
        expected_fee = fill_value * 0.001
        assert abs(fees - expected_fee) < 0.01
    
    @pytest.mark.asyncio
    async def test_extract_avg_price_from_avg_price(self, order_status_poller):
        """Test extracting average price from avgPrice field."""
        status_data = {
            'avgPrice': '42000.0',
            'executedQty': '0.1'
        }
        
        avg_price = order_status_poller._extract_avg_price(status_data)
        
        assert avg_price == 42000.0
    
    @pytest.mark.asyncio
    async def test_extract_avg_price_from_price(self, order_status_poller):
        """Test extracting average price from price field."""
        status_data = {
            'price': '42000.0',
            'executedQty': '0.1'
        }
        
        avg_price = order_status_poller._extract_avg_price(status_data)
        
        assert avg_price == 42000.0
    
    @pytest.mark.asyncio
    async def test_extract_avg_price_from_fills(self, order_status_poller):
        """Test extracting average price from fills array."""
        status_data = {
            'fills': [
                {'price': '42000.0', 'qty': '0.05'},
                {'price': '42010.0', 'qty': '0.05'}
            ]
        }
        
        avg_price = order_status_poller._extract_avg_price(status_data)
        
        # Weighted average: (42000*0.05 + 42010*0.05) / 0.1 = 42005
        assert abs(avg_price - 42005.0) < 0.01
    
    @pytest.mark.asyncio
    async def test_extract_fill_time_from_update_time(self, order_status_poller):
        """Test extracting fill time from updateTime."""
        status_data = {
            'updateTime': 1640000000000  # Milliseconds
        }
        
        fill_time = order_status_poller._extract_fill_time(status_data)
        
        assert isinstance(fill_time, datetime)
        # Should convert milliseconds to datetime
        expected_time = datetime.fromtimestamp(1640000000)
        assert abs((fill_time - expected_time).total_seconds()) < 1
    
    @pytest.mark.asyncio
    async def test_extract_fill_time_default(self, order_status_poller):
        """Test default fill time when not available."""
        status_data = {}
        
        fill_time = order_status_poller._extract_fill_time(status_data)
        
        assert isinstance(fill_time, datetime)
        # Should be recent (within last second)
        assert abs((datetime.now() - fill_time).total_seconds()) < 1
    
    @pytest.mark.asyncio
    async def test_wait_for_fill_error_retry(self, order_status_poller, sample_order, mock_exchange):
        """Test error handling and retry."""
        call_count = 0
        
        async def mock_get_order_status(symbol, order_id):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("API error")
            return {
                'status': 'FILLED',
                'executedQty': '0.1',
                'price': '42000.0',
                'avgPrice': '42000.0',
                'updateTime': 1640000000000,
                'fills': []
            }
        
        mock_exchange.get_order_status = AsyncMock(side_effect=mock_get_order_status)
        
        result = await order_status_poller.wait_for_fill(sample_order, timeout=1)
        
        assert result.status == 'FILLED'
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_wait_for_fill_max_retries(self, order_status_poller, sample_order, mock_exchange):
        """Test max retries exceeded."""
        # Create poller with very short interval but long enough timeout
        # to allow 3 retries before timeout
        fast_poller = OrderStatusPoller(
            exchange=mock_exchange,
            poll_interval_seconds=0.01,  # Very fast polling
            default_timeout_seconds=10  # Long enough timeout
        )
        
        call_count = {'count': 0}
        
        async def mock_get_order_status_error(symbol, order_id):
            call_count['count'] += 1
            raise Exception(f"Persistent error {call_count['count']}")
        
        mock_exchange.get_order_status = AsyncMock(side_effect=mock_get_order_status_error)
        
        # Should raise OrderStatusError after 3 consecutive errors
        with pytest.raises(OrderStatusError, match="Failed to check order status after 3 consecutive errors"):
            await fast_poller.wait_for_fill(sample_order, timeout=10)
        
        # Verify exactly 3 calls were made (check after exception is caught)
        assert call_count['count'] == 3, f"Expected 3 calls, got {call_count['count']}"
    
    @pytest.mark.asyncio
    async def test_wait_for_fill_timeout_with_final_check(self, order_status_poller, sample_order, mock_exchange):
        """Test timeout with final status check."""
        # First calls return NEW, final call returns FILLED
        call_count = 0
        
        async def mock_get_order_status(symbol, order_id):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:  # First 3 calls return NEW
                return {
                    'status': 'NEW',
                    'executedQty': '0',
                    'updateTime': 1640000000000
                }
            # Final call (after timeout) returns FILLED
            return {
                'status': 'FILLED',
                'executedQty': '0.1',
                'price': '42000.0',
                'avgPrice': '42000.0',
                'updateTime': 1640000000000,
                'fills': []
            }
        
        mock_exchange.get_order_status = AsyncMock(side_effect=mock_get_order_status)
        
        # Use longer timeout to allow multiple polls
        result = await order_status_poller.wait_for_fill(sample_order, timeout=0.5)
        
        # Should detect FILLED in final check (after timeout)
        assert result.status == 'FILLED'
