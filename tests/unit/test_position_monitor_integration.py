"""
Integration tests for PositionMonitor - Real SL/TP monitoring.

Tests:
- Stop-loss triggering for LONG positions
- Stop-loss triggering for SHORT positions
- Take-profit triggering
- Position closure execution
- Adverse conditions detection
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.position_monitor import PositionMonitor
from src.core.exchange import BinanceExchange
from src.execution.lifecycle import OrderLifecycleManager
from src.risk.manager import RiskManager


@pytest.fixture
def mock_exchange():
    """Mock BinanceExchange."""
    exchange = AsyncMock(spec=BinanceExchange)
    exchange.get_ticker_price = AsyncMock()
    exchange.place_order = AsyncMock()
    exchange.get_order_status = AsyncMock()
    exchange.get_order_book = AsyncMock()
    return exchange


@pytest.fixture
def mock_risk_manager():
    """Mock RiskManager with positions."""
    risk_manager = MagicMock(spec=RiskManager)
    risk_manager.open_positions = []

    # Make remove_position actually remove from list
    def remove_position_impl(position_id):
        risk_manager.open_positions[:] = [
            p for p in risk_manager.open_positions
            if p.get('id') != position_id
        ]

    risk_manager.remove_position = MagicMock(side_effect=remove_position_impl)
    return risk_manager


@pytest.fixture
def mock_order_lifecycle():
    """Mock OrderLifecycleManager."""
    return MagicMock(spec=OrderLifecycleManager)


@pytest.fixture
async def position_monitor(mock_risk_manager, mock_exchange, mock_order_lifecycle):
    """Create PositionMonitor instance."""
    monitor = PositionMonitor(
        risk_manager=mock_risk_manager,
        exchange=mock_exchange,
        order_lifecycle=mock_order_lifecycle,
        check_interval=1.0  # 1 second for fast testing
    )
    yield monitor
    # Cleanup
    await monitor.stop()


@pytest.mark.asyncio
async def test_stop_loss_triggers_for_long_position(
    position_monitor,
    mock_exchange,
    mock_risk_manager
):
    """Test that stop-loss triggers when price drops below SL for LONG position."""
    # Arrange
    position = {
        'id': 'test-pos-1',
        'symbol': 'BTCUSDT',
        'side': 'BUY',
        'entry_price': 50000.0,
        'stop_loss': 49000.0,
        'take_profit': 52000.0,
        'quantity': 0.01,
        'opened_at': datetime.now()
    }
    mock_risk_manager.open_positions = [position]

    # Price drops to 48500 (below SL)
    mock_exchange.get_ticker_price.return_value = 48500.0

    # Mock order placement response
    mock_exchange.place_order.return_value = {'orderId': 12345}
    mock_exchange.get_order_status.return_value = {
        'status': 'FILLED',
        'executedQty': '0.01',
        'price': '48500.0'
    }

    # Act
    await position_monitor.start()
    await asyncio.sleep(4)  # Wait for check cycle + order status check (2s sleep in code)
    await position_monitor.stop()

    # Assert
    # Should have called get_ticker_price for BTCUSDT
    mock_exchange.get_ticker_price.assert_called()

    # Should have placed SELL order to close LONG position
    mock_exchange.place_order.assert_called_once()
    call_args = mock_exchange.place_order.call_args
    assert call_args.kwargs['symbol'] == 'BTCUSDT'
    assert call_args.kwargs['side'] == 'SELL'
    assert call_args.kwargs['order_type'] == 'MARKET'
    assert call_args.kwargs['quantity'] == 0.01

    # Should have checked order status
    mock_exchange.get_order_status.assert_called_once()

    # Should have removed position from risk manager
    mock_risk_manager.remove_position.assert_called_once_with('test-pos-1')


@pytest.mark.asyncio
async def test_stop_loss_triggers_for_short_position(
    position_monitor,
    mock_exchange,
    mock_risk_manager
):
    """Test that stop-loss triggers when price rises above SL for SHORT position."""
    # Arrange
    position = {
        'id': 'test-pos-2',
        'symbol': 'ETHUSDT',
        'side': 'SELL',
        'entry_price': 3000.0,
        'stop_loss': 3100.0,
        'take_profit': 2800.0,
        'quantity': 0.5,
        'opened_at': datetime.now()
    }
    mock_risk_manager.open_positions = [position]

    # Price rises to 3150 (above SL)
    mock_exchange.get_ticker_price.return_value = 3150.0

    # Mock order placement
    mock_exchange.place_order.return_value = {'orderId': 12346}
    mock_exchange.get_order_status.return_value = {
        'status': 'FILLED',
        'executedQty': '0.5',
        'price': '3150.0'
    }

    # Act
    await position_monitor.start()
    await asyncio.sleep(4)  # Wait for check cycle + order status check
    await position_monitor.stop()

    # Assert
    mock_exchange.place_order.assert_called_once()
    call_args = mock_exchange.place_order.call_args
    assert call_args.kwargs['symbol'] == 'ETHUSDT'
    assert call_args.kwargs['side'] == 'BUY'  # Close SHORT with BUY
    assert call_args.kwargs['order_type'] == 'MARKET'

    mock_exchange.get_order_status.assert_called_once()
    mock_risk_manager.remove_position.assert_called_once_with('test-pos-2')


@pytest.mark.asyncio
async def test_take_profit_triggers_for_long_position(
    position_monitor,
    mock_exchange,
    mock_risk_manager
):
    """Test that take-profit triggers when price rises above TP for LONG position."""
    # Arrange
    position = {
        'id': 'test-pos-3',
        'symbol': 'BTCUSDT',
        'side': 'BUY',
        'entry_price': 50000.0,
        'stop_loss': 49000.0,
        'take_profit': 52000.0,
        'quantity': 0.02,
        'opened_at': datetime.now()
    }
    mock_risk_manager.open_positions = [position]

    # Price rises to 52500 (above TP)
    mock_exchange.get_ticker_price.return_value = 52500.0

    mock_exchange.place_order.return_value = {'orderId': 12347}
    mock_exchange.get_order_status.return_value = {
        'status': 'FILLED',
        'executedQty': '0.02',
        'price': '52500.0'
    }

    # Act
    await position_monitor.start()
    await asyncio.sleep(4)  # Wait for check cycle + order status check
    await position_monitor.stop()

    # Assert
    mock_exchange.place_order.assert_called_once()
    call_args = mock_exchange.place_order.call_args
    assert call_args.kwargs['side'] == 'SELL'

    mock_exchange.get_order_status.assert_called_once()
    mock_risk_manager.remove_position.assert_called_once_with('test-pos-3')


@pytest.mark.asyncio
async def test_no_action_when_price_in_range(
    position_monitor,
    mock_exchange,
    mock_risk_manager
):
    """Test that no action is taken when price is between SL and TP."""
    # Arrange
    position = {
        'id': 'test-pos-4',
        'symbol': 'BTCUSDT',
        'side': 'BUY',
        'entry_price': 50000.0,
        'stop_loss': 49000.0,
        'take_profit': 52000.0,
        'quantity': 0.01,
        'opened_at': datetime.now()
    }
    mock_risk_manager.open_positions = [position]

    # Price is at 50500 (between SL and TP)
    mock_exchange.get_ticker_price.return_value = 50500.0

    # Act
    await position_monitor.start()
    await asyncio.sleep(2)
    await position_monitor.stop()

    # Assert
    # Should have checked price but NOT placed any orders
    mock_exchange.get_ticker_price.assert_called()
    mock_exchange.place_order.assert_not_called()
    mock_risk_manager.remove_position.assert_not_called()


@pytest.mark.asyncio
async def test_handles_price_fetch_error_gracefully(
    position_monitor,
    mock_exchange,
    mock_risk_manager
):
    """Test that monitor continues running even if price fetch fails."""
    # Arrange
    position = {
        'id': 'test-pos-5',
        'symbol': 'BTCUSDT',
        'side': 'BUY',
        'entry_price': 50000.0,
        'stop_loss': 49000.0,
        'quantity': 0.01,
        'opened_at': datetime.now()
    }
    mock_risk_manager.open_positions = [position]

    # First call fails, second succeeds
    mock_exchange.get_ticker_price.side_effect = [
        Exception("Network error"),
        50500.0
    ]

    # Act
    await position_monitor.start()
    await asyncio.sleep(3)  # Wait for 2+ cycles
    await position_monitor.stop()

    # Assert
    # Should have tried to fetch price multiple times
    assert mock_exchange.get_ticker_price.call_count >= 2

    # Should NOT have crashed
    assert position_monitor.running is False  # Stopped gracefully


@pytest.mark.asyncio
async def test_start_stop_idempotency(position_monitor):
    """Test that start() and stop() can be called multiple times safely."""
    # Can start multiple times
    await position_monitor.start()
    await position_monitor.start()  # Second call should be no-op
    assert position_monitor.running is True

    # Can stop multiple times
    await position_monitor.stop()
    await position_monitor.stop()  # Second call should be no-op
    assert position_monitor.running is False


@pytest.mark.asyncio
async def test_check_interval_validation():
    """Test that invalid check_interval raises ValueError."""
    mock_rm = MagicMock(spec=RiskManager)
    mock_ex = AsyncMock(spec=BinanceExchange)
    mock_ol = MagicMock(spec=OrderLifecycleManager)

    # Should raise ValueError for check_interval <= 0
    with pytest.raises(ValueError, match="check_interval must be > 0"):
        PositionMonitor(
            risk_manager=mock_rm,
            exchange=mock_ex,
            order_lifecycle=mock_ol,
            check_interval=0.0
        )

    with pytest.raises(ValueError, match="check_interval must be > 0"):
        PositionMonitor(
            risk_manager=mock_rm,
            exchange=mock_ex,
            order_lifecycle=mock_ol,
            check_interval=-1.0
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
