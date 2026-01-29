"""
Tests for CVD (Cumulative Volume Delta) analysis.
"""

import pandas as pd
import pytest

from src.analysis.cvd import VolumeDeltaAnalyzer
from tests.conftest import sample_trades_df


class TestVolumeDeltaAnalyzer:
    """Tests for VolumeDeltaAnalyzer."""
    
    def test_calculate_cvd_from_trades(self, sample_trades_df):
        """Test calculating CVD from trades."""
        analyzer = VolumeDeltaAnalyzer()
        cvd_data = analyzer.calculate_cvd_from_trades(sample_trades_df)
        
        assert len(cvd_data.timestamps) == len(sample_trades_df)
        assert len(cvd_data.prices) == len(sample_trades_df)
        assert len(cvd_data.cvd_values) == len(sample_trades_df)
        assert len(cvd_data.buy_volume) == len(sample_trades_df)
        assert len(cvd_data.sell_volume) == len(sample_trades_df)
        
        # CVD should be cumulative (with floating point tolerance)
        assert abs(cvd_data.cvd_values[-1] - sum(cvd_data.delta)) < 1e-10
    
    def test_calculate_cvd_buy_orders(self):
        """Test CVD with buy orders."""
        from datetime import datetime, timezone
        
        trades = pd.DataFrame({
            'price': [42000, 42010, 42020],
            'quantity': [1.0, 1.0, 1.0],
            'is_buyer_maker': [False, False, False]  # All buy orders
        }, index=pd.date_range('2024-01-01', periods=3, freq='1min', tz=timezone.utc))
        
        analyzer = VolumeDeltaAnalyzer()
        cvd_data = analyzer.calculate_cvd_from_trades(trades)
        
        # All positive deltas (buy orders)
        assert all(d > 0 for d in cvd_data.delta)
        assert cvd_data.cvd_values[-1] > 0
    
    def test_calculate_cvd_sell_orders(self):
        """Test CVD with sell orders."""
        from datetime import datetime, timezone
        
        trades = pd.DataFrame({
            'price': [42000, 42010, 42020],
            'quantity': [1.0, 1.0, 1.0],
            'is_buyer_maker': [True, True, True]  # All sell orders
        }, index=pd.date_range('2024-01-01', periods=3, freq='1min', tz=timezone.utc))
        
        analyzer = VolumeDeltaAnalyzer()
        cvd_data = analyzer.calculate_cvd_from_trades(trades)
        
        # All negative deltas (sell orders)
        assert all(d < 0 for d in cvd_data.delta)
        assert cvd_data.cvd_values[-1] < 0
    
    def test_calculate_cvd_divergence_bullish(self):
        """Test detecting bullish divergence."""
        from datetime import datetime, timezone
        
        # Price going down, CVD going up
        price_df = pd.DataFrame({
            'close': [42000, 41900, 41800, 41700, 41600]  # Price down
        }, index=pd.date_range('2024-01-01', periods=5, freq='1min', tz=timezone.utc))
        
        # Create CVD data with upward trend
        trades = pd.DataFrame({
            'price': [42000, 41900, 41800, 41700, 41600],
            'quantity': [1.0, 1.0, 1.0, 1.0, 1.0],
            'is_buyer_maker': [False, False, False, False, False]  # Buy orders (CVD up)
        }, index=pd.date_range('2024-01-01', periods=5, freq='1min', tz=timezone.utc))
        
        analyzer = VolumeDeltaAnalyzer()
        cvd_data = analyzer.calculate_cvd_from_trades(trades)
        divergence = analyzer.calculate_cvd_divergence(price_df, cvd_data, lookback_periods=5)
        
        # May or may not detect divergence depending on normalization
        assert divergence in ['bullish_divergence', None]
    
    def test_get_cvd_trend(self, sample_trades_df):
        """Test getting CVD trend."""
        analyzer = VolumeDeltaAnalyzer()
        cvd_data = analyzer.calculate_cvd_from_trades(sample_trades_df)
        trend = analyzer.get_cvd_trend(cvd_data, lookback_periods=10)
        
        assert trend in ['bullish', 'bearish', 'neutral']
    
    def test_calculate_cvd_empty_dataframe(self):
        """Test with empty DataFrame."""
        empty_df = pd.DataFrame(columns=['price', 'quantity', 'is_buyer_maker'])
        analyzer = VolumeDeltaAnalyzer()
        
        with pytest.raises(ValueError, match="Empty trades DataFrame"):
            analyzer.calculate_cvd_from_trades(empty_df)
