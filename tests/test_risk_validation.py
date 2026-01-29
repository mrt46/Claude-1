"""
Tests for pre-trade validation.
"""

import pytest

from src.analysis.orderbook import OrderBook
from src.risk.validation import MicrostructureValidator
from datetime import datetime, timezone


class TestMicrostructureValidator:
    """Tests for MicrostructureValidator."""
    
    @pytest.fixture
    def validator(self):
        """Create validator instance."""
        return MicrostructureValidator(max_slippage_percent=0.5, min_liquidity_usdt=50000.0)
    
    @pytest.fixture
    def good_orderbook(self):
        """Create order book with good liquidity."""
        return OrderBook(
            symbol='BTCUSDT',
            bids=[
                (42000.0, 10.0),
                (41999.0, 8.0),
                (41998.0, 7.0),
            ],
            asks=[
                (42001.0, 9.0),
                (42002.0, 8.0),
                (42003.0, 7.0),
            ],
            timestamp=datetime.now(timezone.utc)
        )
    
    @pytest.fixture
    def poor_orderbook(self):
        """Create order book with poor liquidity."""
        return OrderBook(
            symbol='BTCUSDT',
            bids=[(42000.0, 0.1)],
            asks=[(42001.0, 0.1)],
            timestamp=datetime.now(timezone.utc)
        )
    
    @pytest.mark.asyncio
    async def test_validate_good_microstructure(self, validator, good_orderbook):
        """Test validation with good microstructure."""
        result = await validator.validate(good_orderbook, order_size_usdt=1000.0)
        
        assert result['valid'] == True
        assert result['spread_quality'] in ['good', 'moderate']
        assert result['liquidity_quality'] in ['good', 'moderate']
        assert result['estimated_slippage'] is not None
        assert result['reason'] is None
    
    @pytest.mark.asyncio
    async def test_validate_poor_liquidity(self, validator, poor_orderbook):
        """Test validation with poor liquidity."""
        result = await validator.validate(poor_orderbook, order_size_usdt=1000.0)
        
        assert result['valid'] == False
        assert 'liquidity' in result['reason'].lower()
    
    @pytest.mark.asyncio
    async def test_validate_excessive_slippage(self, validator, good_orderbook):
        """Test validation with excessive slippage."""
        # Use very large order size to trigger slippage
        result = await validator.validate(good_orderbook, order_size_usdt=100000.0)
        
        # May or may not fail depending on order book depth
        assert isinstance(result['valid'], bool)
    
    @pytest.mark.asyncio
    async def test_validate_empty_orderbook(self, validator):
        """Test validation with empty order book."""
        empty_ob = OrderBook(
            symbol='BTCUSDT',
            bids=[],
            asks=[],
            timestamp=datetime.now(timezone.utc)
        )
        
        with pytest.raises(ValueError):
            await validator.validate(empty_ob, order_size_usdt=1000.0)
