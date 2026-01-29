"""
Tests for base strategy class.
"""

from datetime import datetime, timezone

import pandas as pd
import pytest

from src.strategies.base import BaseStrategy, Signal


class ConcreteStrategy(BaseStrategy):
    """Concrete strategy for testing."""
    
    async def generate_signal(self, df, **kwargs):
        """Generate test signal."""
        if len(df) > 0:
            return Signal(
                strategy=self.name,
                symbol='BTCUSDT',
                side='BUY',
                entry_price=42000.0,
                stop_loss=41000.0,
                take_profit=44000.0,
                confidence=0.8,
                timestamp=datetime.now(timezone.utc),
                metadata={}
            )
        return None


class TestBaseStrategy:
    """Tests for BaseStrategy."""
    
    def test_strategy_initialization(self):
        """Test strategy initialization."""
        strategy = ConcreteStrategy("TestStrategy", {})
        
        assert strategy.name == "TestStrategy"
        assert strategy.config == {}
        assert strategy.logger is not None
    
    def test_validate_signal_valid_buy(self):
        """Test validating valid BUY signal."""
        strategy = ConcreteStrategy("TestStrategy", {})
        
        signal = Signal(
            strategy="TestStrategy",
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42000.0,
            stop_loss=41000.0,  # Below entry
            take_profit=44000.0,  # Above entry
            confidence=0.8,
            timestamp=datetime.now(timezone.utc),
            metadata={}
        )
        
        assert strategy.validate_signal(signal) == True
    
    def test_validate_signal_valid_sell(self):
        """Test validating valid SELL signal."""
        strategy = ConcreteStrategy("TestStrategy", {})
        
        signal = Signal(
            strategy="TestStrategy",
            symbol='BTCUSDT',
            side='SELL',
            entry_price=42000.0,
            stop_loss=43000.0,  # Above entry
            take_profit=40000.0,  # Below entry
            confidence=0.8,
            timestamp=datetime.now(timezone.utc),
            metadata={}
        )
        
        assert strategy.validate_signal(signal) == True
    
    def test_validate_signal_invalid_confidence(self):
        """Test validating signal with invalid confidence."""
        strategy = ConcreteStrategy("TestStrategy", {})
        
        signal = Signal(
            strategy="TestStrategy",
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42000.0,
            stop_loss=41000.0,
            take_profit=44000.0,
            confidence=1.5,  # Invalid (> 1.0)
            timestamp=datetime.now(timezone.utc),
            metadata={}
        )
        
        assert strategy.validate_signal(signal) == False
    
    def test_validate_signal_invalid_stop_loss_buy(self):
        """Test validating BUY signal with invalid stop loss."""
        strategy = ConcreteStrategy("TestStrategy", {})
        
        signal = Signal(
            strategy="TestStrategy",
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42000.0,
            stop_loss=43000.0,  # Above entry (invalid)
            take_profit=44000.0,
            confidence=0.8,
            timestamp=datetime.now(timezone.utc),
            metadata={}
        )
        
        assert strategy.validate_signal(signal) == False
    
    def test_validate_signal_invalid_take_profit_buy(self):
        """Test validating BUY signal with invalid take profit."""
        strategy = ConcreteStrategy("TestStrategy", {})
        
        signal = Signal(
            strategy="TestStrategy",
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42000.0,
            stop_loss=41000.0,
            take_profit=40000.0,  # Below entry (invalid)
            confidence=0.8,
            timestamp=datetime.now(timezone.utc),
            metadata={}
        )
        
        assert strategy.validate_signal(signal) == False
    
    @pytest.mark.asyncio
    async def test_generate_signal(self):
        """Test generating signal."""
        strategy = ConcreteStrategy("TestStrategy", {})
        
        df = pd.DataFrame({
            'close': [42000, 42100, 42200],
            'volume': [100, 110, 120]
        })
        
        signal = await strategy.generate_signal(df)
        
        assert signal is not None
        assert signal.side == 'BUY'
        assert signal.entry_price == 42000.0
    
    @pytest.mark.asyncio
    async def test_generate_signal_empty_df(self):
        """Test generating signal with empty DataFrame."""
        strategy = ConcreteStrategy("TestStrategy", {})
        
        df = pd.DataFrame()
        
        signal = await strategy.generate_signal(df)
        
        assert signal is None
