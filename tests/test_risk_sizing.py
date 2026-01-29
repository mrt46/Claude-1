"""
Tests for position sizing.
"""

import pytest

from src.risk.sizing import PositionSizer


class TestPositionSizer:
    """Tests for PositionSizer."""
    
    def test_calculate_position_size_buy(self):
        """Test calculating position size for BUY."""
        sizer = PositionSizer(risk_per_trade_percent=2.0)
        
        result = sizer.calculate_position_size(
            account_balance=10000.0,
            entry_price=42000.0,
            stop_loss=41000.0,
            side='BUY'
        )
        
        assert result['quantity'] > 0
        assert result['position_value_usdt'] > 0
        assert result['risk_amount_usdt'] == 200.0  # 2% of 10000
        assert result['risk_per_unit'] == 1000.0  # 42000 - 41000
        assert result['risk_reward_ratio'] == 2.0
    
    def test_calculate_position_size_sell(self):
        """Test calculating position size for SELL."""
        sizer = PositionSizer(risk_per_trade_percent=2.0)
        
        result = sizer.calculate_position_size(
            account_balance=10000.0,
            entry_price=42000.0,
            stop_loss=43000.0,
            side='SELL'
        )
        
        assert result['quantity'] > 0
        assert result['risk_per_unit'] == 1000.0  # 43000 - 42000
        assert result['risk_amount_usdt'] == 200.0
    
    def test_calculate_position_size_max_limit(self):
        """Test position size respects max limit."""
        sizer = PositionSizer(
            risk_per_trade_percent=10.0,  # 10% risk
            max_position_size_usdt=5000.0
        )
        
        result = sizer.calculate_position_size(
            account_balance=10000.0,
            entry_price=42000.0,
            stop_loss=41000.0,
            side='BUY'
        )
        
        # Should be capped at max_position_size_usdt
        assert result['position_value_usdt'] <= 5000.0
    
    def test_calculate_position_size_min_limit(self):
        """Test position size respects min limit."""
        sizer = PositionSizer(
            risk_per_trade_percent=0.01,  # Very small risk (0.01%)
            min_position_size_usdt=10.0
        )
        
        # This should raise error if position too small and cannot be increased
        try:
            result = sizer.calculate_position_size(
                account_balance=1000.0,
                entry_price=42000.0,
                stop_loss=41900.0,  # Small risk
                side='BUY'
            )
            # If it doesn't raise, check that position is at least min size
            assert result['position_value_usdt'] >= sizer.min_position_size_usdt
        except ValueError as e:
            # It's okay if it raises ValueError for too small position
            assert "too small" in str(e).lower()
    
    def test_calculate_position_size_invalid_stop_loss_buy(self):
        """Test invalid stop loss for BUY."""
        sizer = PositionSizer()
        
        with pytest.raises(ValueError, match="Invalid stop loss"):
            sizer.calculate_position_size(
                account_balance=10000.0,
                entry_price=42000.0,
                stop_loss=43000.0,  # Stop loss above entry (invalid for BUY)
                side='BUY'
            )
    
    def test_calculate_position_size_invalid_stop_loss_sell(self):
        """Test invalid stop loss for SELL."""
        sizer = PositionSizer()
        
        with pytest.raises(ValueError, match="Invalid stop loss"):
            sizer.calculate_position_size(
                account_balance=10000.0,
                entry_price=42000.0,
                stop_loss=41000.0,  # Stop loss below entry (invalid for SELL)
                side='SELL'
            )
