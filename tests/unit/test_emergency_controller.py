"""
Unit tests for EmergencyController.

Tests emergency trigger detection, position closure, and kill switch.
"""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from src.core.emergency_controller import EmergencyController
from src.risk.manager import RiskManager
from src.core.exchange import BinanceExchange


class TestEmergencyController:
    """Unit tests for EmergencyController"""
    
    @pytest.fixture
    def mock_risk_manager(self):
        """Create mock RiskManager"""
        rm = Mock(spec=RiskManager)
        rm.open_positions = []
        rm.daily_pnl = 0.0
        rm.daily_start_balance = 10000.0
        rm.max_balance = 10000.0
        rm.update_daily_pnl = Mock()
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
    def temp_kill_switch_file(self):
        """Create temporary kill switch file path (but not the file itself)"""
        # Generate a unique path without creating the file
        # This way the kill switch is not triggered unless explicitly created
        temp_path = tempfile.mktemp(prefix='kill_switch_test_')
        yield temp_path
        # Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)
    
    @pytest.fixture
    def controller(self, mock_risk_manager, mock_exchange, temp_kill_switch_file):
        """Create EmergencyController instance"""
        return EmergencyController(
            risk_manager=mock_risk_manager,
            exchange=mock_exchange,
            max_daily_loss_percent=0.05,  # 5%
            max_single_position_loss_percent=0.10,  # 10%
            kill_switch_file=temp_kill_switch_file
        )
    
    def test_init(self, controller):
        """Test initialization"""
        assert controller.emergency_mode == False
        assert controller.trading_paused == False
        assert controller.max_daily_loss_percent == 0.05
        assert controller.max_single_position_loss_percent == 0.10
    
    def test_init_invalid_daily_loss(self, mock_risk_manager, mock_exchange):
        """Test initialization with invalid daily loss"""
        with pytest.raises(ValueError, match="max_daily_loss_percent must be between 0 and 1.0"):
            EmergencyController(
                risk_manager=mock_risk_manager,
                exchange=mock_exchange,
                max_daily_loss_percent=1.5  # Invalid
            )
    
    def test_init_invalid_single_loss(self, mock_risk_manager, mock_exchange):
        """Test initialization with invalid single position loss"""
        with pytest.raises(ValueError, match="max_single_position_loss_percent"):
            EmergencyController(
                risk_manager=mock_risk_manager,
                exchange=mock_exchange,
                max_single_position_loss_percent=-0.1  # Invalid
            )
    
    @pytest.mark.asyncio
    async def test_emergency_triggered_on_daily_loss(self, controller, mock_risk_manager):
        """Test emergency triggers when daily loss exceeds threshold"""
        # Set up big loss
        mock_risk_manager.daily_pnl = -600.0  # -6% loss
        mock_risk_manager.daily_start_balance = 10000.0
        
        # Mock trigger_emergency_stop
        controller.trigger_emergency_stop = AsyncMock()
        
        # Check triggers
        result = await controller.check_emergency_triggers(current_balance=9400.0)
        
        assert result == True
        controller.trigger_emergency_stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_no_emergency_on_small_loss(self, controller, mock_risk_manager):
        """Test no emergency on small loss"""
        # Set up small loss scenario (-2%, below 5% threshold)
        mock_risk_manager.daily_start_balance = 10000.0
        
        # Mock update_daily_pnl to set daily_pnl to -200 (2% loss)
        def mock_update_pnl(balance):
            mock_risk_manager.daily_pnl = balance - mock_risk_manager.daily_start_balance
        
        mock_risk_manager.update_daily_pnl = Mock(side_effect=mock_update_pnl)
        mock_risk_manager.open_positions = []  # No positions to check
        
        controller.trigger_emergency_stop = AsyncMock()
        
        # Current balance = 9800 (2% loss, below 5% threshold)
        result = await controller.check_emergency_triggers(current_balance=9800.0)
        
        # Should not trigger emergency
        assert result == False
        controller.trigger_emergency_stop.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_emergency_triggered_on_exact_threshold(self, controller, mock_risk_manager):
        """Test emergency triggers at exact threshold"""
        mock_risk_manager.daily_pnl = -500.0  # Exactly -5%
        mock_risk_manager.daily_start_balance = 10000.0
        
        controller.trigger_emergency_stop = AsyncMock()
        
        result = await controller.check_emergency_triggers(current_balance=9500.0)
        
        # Should trigger (loss is >= threshold)
        assert result == True
        controller.trigger_emergency_stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_emergency_triggered_on_single_position_loss(
        self,
        controller,
        mock_risk_manager,
        mock_exchange
    ):
        """Test emergency triggers on single position big loss"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'quantity': 0.1,
            'position_value_usdt': 4200.0
        }
        
        mock_risk_manager.open_positions = [position]
        mock_exchange.get_ticker_price = AsyncMock(return_value=37800.0)  # -10% loss
        
        controller.trigger_emergency_stop = AsyncMock()
        
        result = await controller.check_emergency_triggers()
        
        assert result == True
        controller.trigger_emergency_stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_no_emergency_on_small_position_loss(
        self,
        controller,
        mock_risk_manager,
        mock_exchange
    ):
        """Test no emergency on small position loss"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'quantity': 0.1,
            'position_value_usdt': 4200.0
        }
        
        mock_risk_manager.open_positions = [position]
        mock_risk_manager.daily_start_balance = 10000.0
        mock_risk_manager.daily_pnl = 0.0  # No daily loss
        
        # Price at 41500 = -1.19% loss (below 10% threshold)
        # Unrealized PnL = (41500 - 42000) * 0.1 = -50
        # Position value = 42000 * 0.1 = 4200
        # PnL% = -50 / 4200 = -1.19% (below 10% threshold)
        mock_exchange.get_ticker_price = AsyncMock(return_value=41500.0)
        
        controller.trigger_emergency_stop = AsyncMock()
        
        result = await controller.check_emergency_triggers()
        
        # Should not trigger emergency (-1.19% > -10%)
        assert result == False
        controller.trigger_emergency_stop.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_kill_switch_file_triggers_emergency(
        self,
        controller,
        temp_kill_switch_file
    ):
        """Test kill switch file triggers emergency"""
        # Create kill switch file
        with open(temp_kill_switch_file, 'w') as f:
            f.write('STOP')
        
        controller.trigger_emergency_stop = AsyncMock()
        
        result = await controller.check_emergency_triggers()
        
        assert result == True
        controller.trigger_emergency_stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_kill_switch_file_not_exists(self, controller):
        """Test no emergency when kill switch file doesn't exist"""
        # Use non-existent file
        controller.kill_switch_file = Path('/tmp/NONEXISTENT_KILL_SWITCH_12345')
        
        controller.trigger_emergency_stop = AsyncMock()
        
        result = await controller.check_emergency_triggers()
        
        assert result == False
        controller.trigger_emergency_stop.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_trigger_emergency_stop(self, controller, mock_risk_manager):
        """Test emergency stop sequence"""
        mock_risk_manager.open_positions = []
        controller.close_all_positions = AsyncMock(return_value={
            'positions_closed': 0,
            'failed_closures': [],
            'total_pnl': 0.0
        })
        
        await controller.trigger_emergency_stop("Test reason")
        
        assert controller.emergency_mode == True
        assert controller.trading_paused == True
        controller.close_all_positions.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_trigger_emergency_stop_already_in_progress(self, controller):
        """Test emergency stop doesn't run twice"""
        controller.emergency_mode = True
        controller.close_all_positions = AsyncMock()
        
        await controller.trigger_emergency_stop("Test reason")
        
        # Should not call close_all_positions again
        controller.close_all_positions.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_close_all_positions_empty(self, controller, mock_risk_manager):
        """Test closing all positions when none exist"""
        mock_risk_manager.open_positions = []
        
        result = await controller.close_all_positions(reason='TEST')
        
        assert result['positions_closed'] == 0
        assert len(result['failed_closures']) == 0
        assert result['total_pnl'] == 0.0
    
    @pytest.mark.asyncio
    async def test_close_all_positions_success(
        self,
        controller,
        mock_risk_manager,
        mock_exchange
    ):
        """Test closing all positions successfully"""
        position1 = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'quantity': 0.1
        }
        position2 = {
            'id': 'test_2',
            'symbol': 'ETHUSDT',
            'side': 'BUY',
            'entry_price': 3000.0,
            'quantity': 1.0
        }
        
        mock_risk_manager.open_positions = [position1, position2]
        mock_exchange.get_ticker_price = AsyncMock(return_value=42000.0)
        mock_exchange.place_order = AsyncMock(return_value={'orderId': '12345'})
        mock_exchange.get_order_status = AsyncMock(return_value={
            'status': 'FILLED',
            'executedQty': '0.1',
            'price': '42000.0'
        })
        
        result = await controller.close_all_positions(reason='TEST')
        
        assert result['positions_closed'] == 2
        assert len(result['failed_closures']) == 0
        assert mock_exchange.place_order.call_count == 2
    
    @pytest.mark.asyncio
    async def test_close_all_positions_partial_failure(
        self,
        controller,
        mock_risk_manager,
        mock_exchange
    ):
        """Test closing positions with some failures"""
        position1 = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'quantity': 0.1
        }
        position2 = {
            'id': 'test_2',
            'symbol': 'ETHUSDT',
            'side': 'BUY',
            'entry_price': 3000.0,
            'quantity': 1.0
        }
        
        mock_risk_manager.open_positions = [position1, position2]
        
        # First position succeeds, second fails
        call_count = 0
        async def mock_place_order(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {'orderId': '12345'}
            else:
                raise Exception("Order failed")
        
        mock_exchange.place_order = AsyncMock(side_effect=mock_place_order)
        mock_exchange.get_ticker_price = AsyncMock(return_value=42000.0)
        mock_exchange.get_order_status = AsyncMock(return_value={
            'status': 'FILLED',
            'executedQty': '0.1',
            'price': '42000.0'
        })
        
        result = await controller.close_all_positions(reason='TEST')
        
        assert result['positions_closed'] == 1
        assert len(result['failed_closures']) == 1
        assert result['failed_closures'][0]['symbol'] == 'ETHUSDT'
    
    @pytest.mark.asyncio
    async def test_close_single_position_success(
        self,
        controller,
        mock_exchange
    ):
        """Test closing single position successfully"""
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
        
        result = await controller._close_single_position(position, reason='TEST')
        
        assert result is not None
        assert 'pnl' in result
        mock_exchange.place_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_single_position_failure(
        self,
        controller,
        mock_exchange
    ):
        """Test closing single position with failure"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'quantity': 0.1
        }
        
        mock_exchange.get_ticker_price = AsyncMock(side_effect=Exception("API error"))
        
        result = await controller._close_single_position(position, reason='TEST')
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_pause_trading(self, controller):
        """Test pausing trading"""
        assert controller.trading_paused == False
        
        await controller.pause_trading()
        
        assert controller.trading_paused == True
    
    @pytest.mark.asyncio
    async def test_pause_trading_already_paused(self, controller):
        """Test pausing when already paused"""
        controller.trading_paused = True
        
        await controller.pause_trading()  # Should not raise
        
        assert controller.trading_paused == True
    
    @pytest.mark.asyncio
    async def test_resume_trading(self, controller):
        """Test resuming trading"""
        controller.trading_paused = True
        controller.emergency_mode = True
        
        await controller.resume_trading()
        
        assert controller.trading_paused == False
        assert controller.emergency_mode == False
    
    @pytest.mark.asyncio
    async def test_resume_trading_already_active(self, controller):
        """Test resuming when already active"""
        controller.trading_paused = False
        
        await controller.resume_trading()  # Should not raise
        
        assert controller.trading_paused == False
    
    def test_is_trading_paused(self, controller):
        """Test is_trading_paused check"""
        assert controller.is_trading_paused() == False
        
        controller.trading_paused = True
        assert controller.is_trading_paused() == True
    
    def test_is_emergency_mode(self, controller):
        """Test is_emergency_mode check"""
        assert controller.is_emergency_mode() == False
        
        controller.emergency_mode = True
        assert controller.is_emergency_mode() == True
    
    def test_create_kill_switch_file(self, controller, temp_kill_switch_file):
        """Test creating kill switch file"""
        controller.kill_switch_file = Path(temp_kill_switch_file)
        
        # Remove if exists
        if controller.kill_switch_file.exists():
            controller.kill_switch_file.unlink()
        
        controller.create_kill_switch_file()
        
        assert controller.kill_switch_file.exists()
    
    def test_remove_kill_switch_file(self, controller, temp_kill_switch_file):
        """Test removing kill switch file"""
        controller.kill_switch_file = Path(temp_kill_switch_file)
        
        # Create file first
        with open(temp_kill_switch_file, 'w') as f:
            f.write('STOP')
        
        controller.remove_kill_switch_file()
        
        assert not controller.kill_switch_file.exists()
    
    @pytest.mark.asyncio
    async def test_check_emergency_triggers_updates_pnl(self, controller, mock_risk_manager):
        """Test check_emergency_triggers updates daily PnL"""
        current_balance = 9500.0
        mock_risk_manager.daily_start_balance = 10000.0
        
        await controller.check_emergency_triggers(current_balance=current_balance)
        
        # Should update daily PnL
        mock_risk_manager.update_daily_pnl.assert_called_once_with(current_balance)
    
    @pytest.mark.asyncio
    async def test_check_emergency_triggers_handles_price_error(
        self,
        controller,
        mock_risk_manager,
        mock_exchange
    ):
        """Test check_emergency_triggers handles price fetch errors"""
        position = {
            'id': 'test_1',
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'entry_price': 42000.0,
            'quantity': 0.1
        }
        
        mock_risk_manager.open_positions = [position]
        mock_risk_manager.daily_start_balance = 10000.0
        mock_risk_manager.daily_pnl = 0.0  # No daily loss
        mock_exchange.get_ticker_price = AsyncMock(return_value=None)  # Price fetch error
        
        controller.trigger_emergency_stop = AsyncMock()
        
        # Should not raise, should skip position check and continue
        result = await controller.check_emergency_triggers()
        
        # Should not trigger emergency on price error (position check skipped)
        # Also check kill switch (should not exist)
        assert result == False
        controller.trigger_emergency_stop.assert_not_called()
