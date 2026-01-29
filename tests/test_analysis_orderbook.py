"""
Tests for order book analysis.
"""

import pytest

from src.analysis.orderbook import OrderBookAnalyzer
from tests.conftest import sample_orderbook


class TestOrderBookAnalyzer:
    """Tests for OrderBookAnalyzer."""
    
    def test_calculate_imbalance(self, sample_orderbook):
        """Test calculating order book imbalance."""
        analyzer = OrderBookAnalyzer()
        imbalance = analyzer.calculate_imbalance(sample_orderbook, depth_levels=5)
        
        assert imbalance.volume_imbalance > 0
        assert imbalance.value_imbalance > 0
        assert imbalance.spread_percent >= 0
        assert imbalance.bid_volume > 0
        assert imbalance.ask_volume > 0
        assert imbalance.interpretation in [
            'strong_buy_pressure',
            'moderate_buy_pressure',
            'balanced',
            'moderate_sell_pressure',
            'strong_sell_pressure'
        ]
    
    def test_calculate_imbalance_strong_buy(self):
        """Test imbalance with strong buy pressure."""
        from src.analysis.orderbook import OrderBook
        from datetime import datetime, timezone
        
        ob = OrderBook(
            symbol='BTCUSDT',
            bids=[(42000, 10.0), (41999, 8.0)],
            asks=[(42001, 1.0), (42002, 1.0)],
            timestamp=datetime.now(timezone.utc)
        )
        
        analyzer = OrderBookAnalyzer()
        imbalance = analyzer.calculate_imbalance(ob, depth_levels=2)
        
        assert imbalance.volume_imbalance > 1.5
        assert imbalance.interpretation == 'strong_buy_pressure'
    
    def test_detect_walls(self, sample_orderbook):
        """Test detecting order book walls."""
        analyzer = OrderBookAnalyzer()
        walls = analyzer.detect_walls(sample_orderbook, threshold_multiplier=3.0)
        
        assert walls.avg_bid_size > 0
        assert walls.avg_ask_size > 0
    
    def test_detect_walls_with_large_orders(self):
        """Test detecting walls with large orders."""
        from src.analysis.orderbook import OrderBook
        from datetime import datetime, timezone
        
        ob = OrderBook(
            symbol='BTCUSDT',
            bids=[
                (42000, 10.0),  # Large order (wall)
                (41999, 1.0),
                (41998, 1.0),
            ],
            asks=[
                (42001, 1.0),
                (42002, 1.0),
            ],
            timestamp=datetime.now(timezone.utc)
        )
        
        analyzer = OrderBookAnalyzer()
        walls = analyzer.detect_walls(ob, threshold_multiplier=3.0)
        
        # Should detect bid wall
        if walls.nearest_bid_wall:
            assert walls.nearest_bid_wall.price == 42000.0
            assert walls.nearest_bid_wall.quantity == 10.0
    
    def test_calculate_liquidity(self, sample_orderbook):
        """Test calculating liquidity."""
        analyzer = OrderBookAnalyzer()
        liquidity = analyzer.calculate_liquidity(sample_orderbook, depth_levels=5)
        
        assert liquidity > 0
    
    def test_assess_liquidity_quality(self):
        """Test assessing liquidity quality."""
        analyzer = OrderBookAnalyzer()
        
        assert analyzer.assess_liquidity_quality(150000) == 'good'
        assert analyzer.assess_liquidity_quality(75000) == 'moderate'
        assert analyzer.assess_liquidity_quality(30000) == 'poor'
    
    def test_calculate_imbalance_empty_orderbook(self):
        """Test with empty order book."""
        from src.analysis.orderbook import OrderBook
        from datetime import datetime, timezone
        
        ob = OrderBook(
            symbol='BTCUSDT',
            bids=[],
            asks=[],
            timestamp=datetime.now(timezone.utc)
        )
        
        analyzer = OrderBookAnalyzer()
        with pytest.raises(ValueError, match="Empty order book"):
            analyzer.calculate_imbalance(ob)
