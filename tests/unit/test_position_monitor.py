"""
Unit tests for PositionMonitor.

Tests SL/TP detection logic, trailing stops, and adverse conditions.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from src.core.position_monitor import PositionMonitor
from src.risk.manager import RiskManager
from src.core.exchange import BinanceExchange
from src.execution.lifecycle import OrderLifecycleManager
from src.data.market_data import MarketDataManager


class TestPositionMonitor:
    """Unit tests for PositionMonitor"""
    
    @pytest.fixture
    def mock_risk_manager(self):
        """Create mock RiskManager"""
        rm = Mock(spec=RiskManager)
        rm.open_positions = []
        rm.remove_position = Mock()
        return rm
    
    @pytest.fixture
    def mock_exchange(self):
        """Create mock Exchange"""
        exchange = Mock(spec=BinanceExchange)
        exchange.get_ticker_price = AsyncMock(return_value=42000.0)
        exchange.place_order = AsyncMock(return_value={'orderId': '12345'})
        exchange.get_order_status = AsyncMock(return_value={
            'status': 'FILLED',
            'executedQty': '0.1',
            'price': '42000.0'
        })
        return exchange
    
    @pytest.fixture
    def mock_order_lifecycle(self):
        """Create mock OrderLifecycleManager"""
        olm = Mock(spec=OrderLifecycleManager)
        return olm
    
    @pytest.fixture
    def mock_market_data(self):
        """Create mock MarketDataManager"""
        md = Mock(spec=MarketDataManager)
        md.get_order_book_snapshot = AsyncMock(return_value={
            'bids': [[42000.0, 1.0], [41999.0, 2.0]],
            'asks': [[42001.0, 1.0], [42002.0, 2.0]]
        })
        return md
    
    @pytest.fixture
    def monitor(
        self,
        mock_risk_manager,
        mock_exchange,
        mock_order_lifecycle,
        mock_market_data
    ):
        """Create PositionMonitor instance"""
        return PositionMonitor(
            risk_manager=mock_risk_manager,
            exchange=mock_exchange,
            order_lifecycle=mock_order_lifecycle,
            market_data=mock_market_data,
            check_interval=1.0,  # Fast for testing
            trailing_stop_enabled=False,
            max_position_age_hours=None,
            adverse_spread_threshold=0.005
        )
    
    def test_init(self, monitor):
        """Test initialization"""
        assert monitor.check_interval == 1.0
        assert monitor.running == False
        assert monitor.monitor_task is None
        assert monitor.trailing_stop_enabled == False
        assert monitor.adverse_spread_threshold == 0.005
    
    def test_init_invalid_check_interval(self, mock_risk_manager, mock_exchange, mock_order_lifecycle):
        """Test initialization with invalid check_interval"""
        with pytest.raises(ValueError, match="check_interval must be > 0"):
            PositionMonitor(
                risk_manager=mock_risk_manager,
                exchange=mock_exchange,
                order_lifecycle=mock_order_lifecycle,
                check_interval=0
            )
    
    @pytest.mark.asyncio
    async def test_start_stop(self, monitor):
        """Test starting and stopping monitor"""
        # Start
        await monitor.start()
        assert monitor.running == True
        assert monitor.monitor_task is not None
        
        # Stop
        await monitor.stop()
        assert monitor.running == False
        assert monitor.monitor_task is None
    
    @pytest.mark.asyncio
    async def test_start_already_running(self, monitor):
        """Test starting when already running"""
        await monitor.start()
        assert monitor.running == True
        
        # Try to start again
        await monitor.start()  # Should not raise, just log warning
        assert monitor.running == True
    
    @pytest.mark.asyncio
    async def test_stop_loss_triggers_long_position(self, monitor):
        """Test stop-loss triggers for long position"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'stop_loss': 41160.0,  # 2% below entry
            'quantity': 0.1
        }
        
        # Price below stop-loss
        result = await monitor._check_stop_loss(position, 41000.0)
        
        assert result == True
    
    @pytest.mark.asyncio
    async def test_stop_loss_triggers_at_exact_price(self, monitor):
        """Test stop-loss triggers at exact stop-loss price"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'stop_loss': 41160.0,
            'quantity': 0.1
        }
        
        # Price exactly at stop-loss
        result = await monitor._check_stop_loss(position, 41160.0)
        
        assert result == True
    
    @pytest.mark.asyncio
    async def test_stop_loss_not_triggered(self, monitor):
        """Test stop-loss doesn't trigger when price above SL"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'stop_loss': 41160.0,
            'quantity': 0.1
        }
        
        # Price still above SL
        result = await monitor._check_stop_loss(position, 41500.0)
        
        assert result == False
    
    @pytest.mark.asyncio
    async def test_stop_loss_short_position(self, monitor):
        """Test stop-loss triggers for short position"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'SELL',
            'entry_price': 42000.0,
            'stop_loss': 42840.0,  # 2% above entry
            'quantity': 0.1
        }
        
        # Price above stop-loss (bad for short)
        result = await monitor._check_stop_loss(position, 43000.0)
        
        assert result == True
    
    @pytest.mark.asyncio
    async def test_stop_loss_no_stop_loss(self, monitor):
        """Test stop-loss check when no stop-loss set"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'stop_loss': None,
            'quantity': 0.1
        }
        
        result = await monitor._check_stop_loss(position, 41000.0)
        
        assert result == False
    
    @pytest.mark.asyncio
    async def test_take_profit_triggers_long_position(self, monitor):
        """Test take-profit triggers for long position"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'stop_loss': 41160.0,
            'take_profit': 42840.0,  # 2% above entry
            'quantity': 0.1
        }
        
        # Price reached TP
        result = await monitor._check_take_profit(position, 42900.0)
        
        assert result == True
    
    @pytest.mark.asyncio
    async def test_take_profit_triggers_at_exact_price(self, monitor):
        """Test take-profit triggers at exact TP price"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'take_profit': 42840.0,
            'quantity': 0.1
        }
        
        # Price exactly at TP
        result = await monitor._check_take_profit(position, 42840.0)
        
        assert result == True
    
    @pytest.mark.asyncio
    async def test_take_profit_not_triggered(self, monitor):
        """Test take-profit doesn't trigger when price below TP"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'take_profit': 42840.0,
            'quantity': 0.1
        }
        
        # Price below TP
        result = await monitor._check_take_profit(position, 42500.0)
        
        assert result == False
    
    @pytest.mark.asyncio
    async def test_take_profit_short_position(self, monitor):
        """Test take-profit triggers for short position"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'SELL',
            'entry_price': 42000.0,
            'take_profit': 41160.0,  # 2% below entry
            'quantity': 0.1
        }
        
        # Price dropped to TP
        result = await monitor._check_take_profit(position, 41000.0)
        
        assert result == True
    
    @pytest.mark.asyncio
    async def test_take_profit_no_take_profit(self, monitor):
        """Test take-profit check when no TP set"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'take_profit': None,
            'quantity': 0.1
        }
        
        result = await monitor._check_take_profit(position, 43000.0)
        
        assert result == False
    
    @pytest.mark.asyncio
    async def test_trailing_stop_updates_long_position(self, monitor):
        """Test trailing stop updates as price moves up"""
        monitor.trailing_stop_enabled = True
        
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'stop_loss': 41160.0,  # 2% below
            'trailing_stop_percent': 0.02,
            'quantity': 0.1,
            'max_price': None
        }
        
        # Price moved up
        await monitor._update_trailing_stop(position, 43000.0)
        
        # New SL should be 2% below new max
        expected_sl = 43000.0 * 0.98  # 42140.0
        
        assert position['stop_loss'] == pytest.approx(expected_sl, rel=0.01)
        assert position['max_price'] == 43000.0
    
    @pytest.mark.asyncio
    async def test_trailing_stop_doesnt_move_down(self, monitor):
        """Test trailing stop doesn't move in unfavorable direction"""
        monitor.trailing_stop_enabled = True
        
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'stop_loss': 42140.0,  # Already moved up
            'trailing_stop_percent': 0.02,
            'quantity': 0.1,
            'max_price': 43000.0
        }
        
        old_sl = position['stop_loss']
        
        # Price dropped (unfavorable)
        await monitor._update_trailing_stop(position, 42500.0)
        
        # SL should not move down
        assert position['stop_loss'] == old_sl
        assert position['max_price'] == 43000.0  # Unchanged
    
    @pytest.mark.asyncio
    async def test_trailing_stop_short_position(self, monitor):
        """Test trailing stop for short position"""
        monitor.trailing_stop_enabled = True
        
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'SELL',
            'entry_price': 42000.0,
            'stop_loss': 42840.0,  # 2% above
            'trailing_stop_percent': 0.02,
            'quantity': 0.1,
            'min_price': None
        }
        
        # Price dropped (favorable for short)
        await monitor._update_trailing_stop(position, 41000.0)
        
        # New SL should be 2% above new min
        expected_sl = 41000.0 * 1.02  # 41820.0
        
        assert position['stop_loss'] == pytest.approx(expected_sl, rel=0.01)
        assert position['min_price'] == 41000.0
    
    @pytest.mark.asyncio
    async def test_trailing_stop_no_trailing_percent(self, monitor):
        """Test trailing stop when no trailing_percent set"""
        monitor.trailing_stop_enabled = True
        
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'stop_loss': 41160.0,
            'trailing_stop_percent': None,
            'quantity': 0.1
        }
        
        # Should not update
        await monitor._update_trailing_stop(position, 43000.0)
        
        assert position['stop_loss'] == 41160.0
    
    @pytest.mark.asyncio
    async def test_adverse_conditions_wide_spread(
        self,
        monitor,
        mock_market_data
    ):
        """Test adverse conditions detected on wide spread"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'quantity': 0.1
        }
        
        # Mock order book with wide spread
        mock_market_data.get_order_book_snapshot = AsyncMock(
            return_value={
                'bids': [[41900.0, 1.0]],  # Best bid
                'asks': [[42500.0, 1.0]]   # Best ask (1.4% spread!)
            }
        )
        
        result = await monitor._check_adverse_conditions(position, 42000.0)
        
        # Should detect wide spread (> 0.5% threshold)
        assert result == True
    
    @pytest.mark.asyncio
    async def test_adverse_conditions_normal_spread(
        self,
        monitor,
        mock_market_data
    ):
        """Test adverse conditions not detected on normal spread"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'quantity': 0.1
        }
        
        # Mock order book with normal spread
        mock_market_data.get_order_book_snapshot = AsyncMock(
            return_value={
                'bids': [[41999.0, 1.0]],  # Best bid
                'asks': [[42001.0, 1.0]]   # Best ask (0.05% spread - normal)
            }
        )
        
        result = await monitor._check_adverse_conditions(position, 42000.0)
        
        # Should not detect adverse conditions
        assert result == False
    
    @pytest.mark.asyncio
    async def test_adverse_conditions_low_liquidity(
        self,
        monitor,
        mock_market_data
    ):
        """Test adverse conditions detected on low liquidity"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'quantity': 0.1
        }
        
        # Mock order book with low liquidity (< $10k)
        mock_market_data.get_order_book_snapshot = AsyncMock(
            return_value={
                'bids': [[42000.0, 0.01], [41999.0, 0.01]],  # Very small
                'asks': [[42001.0, 0.01], [42002.0, 0.01]]
            }
        )
        
        result = await monitor._check_adverse_conditions(position, 42000.0)
        
        # Should detect low liquidity
        assert result == True
    
    @pytest.mark.asyncio
    async def test_adverse_conditions_error_handling(
        self,
        monitor,
        mock_market_data
    ):
        """Test adverse conditions handles errors gracefully"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'quantity': 0.1
        }
        
        # Mock error
        mock_market_data.get_order_book_snapshot = AsyncMock(
            side_effect=Exception("API error")
        )
        
        result = await monitor._check_adverse_conditions(position, 42000.0)
        
        # Should return False on error (don't close position)
        assert result == False
    
    @pytest.mark.asyncio
    async def test_check_position_stop_loss_hit(
        self,
        monitor,
        mock_exchange
    ):
        """Test _check_position closes position when stop-loss hit"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'stop_loss': 41160.0,
            'take_profit': 42840.0,
            'quantity': 0.1
        }
        
        monitor.risk_manager.open_positions = [position]
        mock_exchange.get_ticker_price = AsyncMock(return_value=41000.0)
        
        # Mock close_position_with_reason
        close_mock = AsyncMock()
        monitor._close_position_with_reason = close_mock
        
        await monitor._check_position(position)
        
        # Should call close_position_with_reason
        assert close_mock.called, "_close_position_with_reason should be called"
        assert close_mock.call_count == 1
    
    @pytest.mark.asyncio
    async def test_check_position_take_profit_hit(
        self,
        monitor,
        mock_exchange
    ):
        """Test _check_position closes position when take-profit hit"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'stop_loss': 41160.0,
            'take_profit': 42840.0,
            'quantity': 0.1
        }
        
        monitor.risk_manager.open_positions = [position]
        mock_exchange.get_ticker_price = AsyncMock(return_value=43000.0)
        
        # Mock close_position_with_reason
        close_mock = AsyncMock()
        monitor._close_position_with_reason = close_mock
        
        await monitor._check_position(position)
        
        # Should call close_position_with_reason
        assert close_mock.called, "_close_position_with_reason should be called"
        assert close_mock.call_count == 1
    
    @pytest.mark.asyncio
    async def test_check_position_max_age_exceeded(
        self,
        monitor,
        mock_exchange
    ):
        """Test _check_position closes position when max age exceeded"""
        monitor.max_position_age_hours = 24.0
        
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'stop_loss': 41160.0,
            'take_profit': 42840.0,
            'quantity': 0.1,
            'opened_at': datetime.now() - timedelta(hours=25)  # 25 hours ago
        }
        
        monitor.risk_manager.open_positions = [position]
        mock_exchange.get_ticker_price = AsyncMock(return_value=42000.0)
        
        # Mock close_position_with_reason
        close_mock = AsyncMock()
        monitor._close_position_with_reason = close_mock
        
        await monitor._check_position(position)
        
        # Should call close_position_with_reason
        assert close_mock.called, "_close_position_with_reason should be called"
        assert close_mock.call_count == 1
    
    @pytest.mark.asyncio
    async def test_monitor_loop_no_positions(self, monitor):
        """Test monitor loop with no positions"""
        monitor.risk_manager.open_positions = []
        monitor.running = True
        
        # Run one iteration
        task = asyncio.create_task(monitor._monitor_loop())
        await asyncio.sleep(0.1)  # Let it run briefly
        monitor.running = False
        await asyncio.sleep(0.1)  # Let it stop
        
        # Should complete without error
        assert True
    
    @pytest.mark.asyncio
    async def test_close_position_with_reason(
        self,
        monitor,
        mock_exchange
    ):
        """Test position closure calls exchange"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'quantity': 0.1
        }
        
        mock_exchange.get_ticker_price = AsyncMock(return_value=41000.0)
        mock_exchange.place_order = AsyncMock(return_value={'orderId': '12345'})
        mock_exchange.get_order_status = AsyncMock(return_value={
            'status': 'FILLED',
            'executedQty': '0.1',
            'price': '41000.0'
        })
        
        await monitor._close_position_with_reason(
            position,
            reason='STOP_LOSS_HIT',
            current_price=41000.0
        )
        
        # Verify exchange called
        mock_exchange.place_order.assert_called_once()
        call_args = mock_exchange.place_order.call_args
        assert call_args[1]['symbol'] == 'BTCUSDT'
        assert call_args[1]['side'] == 'SELL'  # Opposite of BUY
        assert call_args[1]['order_type'] == 'MARKET'
        
        # Verify position removed
        monitor.risk_manager.remove_position.assert_called_once_with('test_1')
