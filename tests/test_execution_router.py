"""
Tests for smart order router.
"""

import pytest

from src.execution.router import SmartOrderRouter


class TestSmartOrderRouter:
    """Tests for SmartOrderRouter."""
    
    def test_route_small_order(self):
        """Test routing small order to market."""
        router = SmartOrderRouter()
        result = router.route_order(
            order_size_usdt=500.0,
            liquidity_quality='good',
            spread_quality='good'
        )
        
        assert result['order_type'] == 'market'
        assert 'small order' in result['reason'].lower()
    
    def test_route_medium_order_good_liquidity(self):
        """Test routing medium order to limit."""
        router = SmartOrderRouter()
        result = router.route_order(
            order_size_usdt=3000.0,
            liquidity_quality='good',
            spread_quality='good'
        )
        
        assert result['order_type'] == 'limit'
    
    def test_route_large_order_good_liquidity(self):
        """Test routing large order to TWAP."""
        router = SmartOrderRouter()
        result = router.route_order(
            order_size_usdt=10000.0,
            liquidity_quality='good',
            spread_quality='good'
        )
        
        assert result['order_type'] == 'twap'
        assert result['twap_splits'] is not None
        assert 3 <= result['twap_splits'] <= 5
    
    def test_route_poor_liquidity(self):
        """Test routing with poor liquidity."""
        router = SmartOrderRouter()
        result = router.route_order(
            order_size_usdt=1000.0,
            liquidity_quality='poor',
            spread_quality='good'
        )
        
        assert result['order_type'] == 'reject'
        assert 'liquidity' in result['reason'].lower()
    
    def test_route_custom_thresholds(self):
        """Test routing with custom thresholds."""
        router = SmartOrderRouter(
            small_order_threshold=500.0,
            large_order_threshold=2000.0
        )
        
        # Small order
        result = router.route_order(300.0, 'good', 'good')
        assert result['order_type'] == 'market'
        
        # Large order
        result = router.route_order(5000.0, 'good', 'good')
        assert result['order_type'] == 'twap'
