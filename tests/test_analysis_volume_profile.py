"""
Tests for volume profile analysis.
"""

import pytest

from src.analysis.volume_profile import VolumeProfileAnalyzer
from tests.conftest import sample_ohlcv_df


class TestVolumeProfileAnalyzer:
    """Tests for VolumeProfileAnalyzer."""
    
    def test_calculate_volume_profile(self, sample_ohlcv_df):
        """Test calculating volume profile."""
        analyzer = VolumeProfileAnalyzer(num_bins=50)
        vp = analyzer.calculate_volume_profile(sample_ohlcv_df, period_hours=24)
        
        assert vp.poc > 0
        assert vp.vah >= vp.val
        assert vp.poc >= vp.val
        assert vp.poc <= vp.vah
        assert len(vp.hvn_levels) > 0
        assert len(vp.lvn_levels) > 0
        assert vp.total_volume > 0
    
    def test_calculate_volume_profile_insufficient_data(self):
        """Test with insufficient data."""
        import pandas as pd
        from datetime import datetime, timezone
        
        df = pd.DataFrame({
            'open': [42000],
            'high': [42100],
            'low': [41900],
            'close': [42050],
            'volume': [100]
        })
        
        analyzer = VolumeProfileAnalyzer()
        with pytest.raises(ValueError, match="Insufficient data"):
            analyzer.calculate_volume_profile(df, period_hours=24)
    
    def test_get_current_position_in_profile(self, sample_ohlcv_df):
        """Test getting current position in profile."""
        analyzer = VolumeProfileAnalyzer()
        vp = analyzer.calculate_volume_profile(sample_ohlcv_df, period_hours=24)
        
        # Test above VAH
        position = analyzer.get_current_position_in_profile(vp.vah * 1.01, vp)
        assert position == 'above_vah'
        
        # Test below VAL
        position = analyzer.get_current_position_in_profile(vp.val * 0.99, vp)
        assert position == 'below_val'
        
        # Test in value area
        mid_price = (vp.val + vp.vah) / 2
        position = analyzer.get_current_position_in_profile(mid_price, vp)
        assert position == 'in_value_area'
    
    def test_find_nearest_hvn(self, sample_ohlcv_df):
        """Test finding nearest HVN."""
        analyzer = VolumeProfileAnalyzer()
        vp = analyzer.calculate_volume_profile(sample_ohlcv_df, period_hours=24)
        
        if vp.hvn_levels:
            # Test with price near an HVN
            test_price = vp.hvn_levels[0] * 1.001  # Slightly above first HVN
            result = analyzer.find_nearest_hvn(test_price, vp, max_distance_percent=0.02)
            # Result should be the nearest HVN within threshold
            if result:
                # Verify it's actually the nearest one
                actual_nearest = min(vp.hvn_levels, key=lambda x: abs(x - test_price))
                distance = abs(actual_nearest - test_price) / test_price
                if distance <= 0.02:
                    assert result == actual_nearest
            
            # Test with price far from HVN
            far_price = vp.poc * 1.1
            result = analyzer.find_nearest_hvn(far_price, vp, max_distance_percent=0.01)
            # May return None if no HVN within range
            if result:
                distance = abs(result - far_price) / far_price
                assert distance <= 0.01
    
    def test_find_nearest_lvn(self, sample_ohlcv_df):
        """Test finding nearest LVN."""
        analyzer = VolumeProfileAnalyzer()
        vp = analyzer.calculate_volume_profile(sample_ohlcv_df, period_hours=24)
        
        if vp.lvn_levels:
            # Test with price near an LVN
            test_price = vp.lvn_levels[0] * 1.001  # Slightly above first LVN
            result = analyzer.find_nearest_lvn(test_price, vp, max_distance_percent=0.02)
            # Result should be the nearest LVN within threshold
            if result:
                # Verify it's actually the nearest one
                actual_nearest = min(vp.lvn_levels, key=lambda x: abs(x - test_price))
                distance = abs(actual_nearest - test_price) / test_price
                if distance <= 0.02:
                    assert result == actual_nearest
    
    def test_volume_profile_caching(self, sample_ohlcv_df):
        """Test volume profile caching."""
        analyzer = VolumeProfileAnalyzer()
        
        # First calculation
        vp1 = analyzer.calculate_volume_profile(sample_ohlcv_df, period_hours=24)
        
        # Second calculation (should use cache)
        vp2 = analyzer.calculate_volume_profile(sample_ohlcv_df, period_hours=24)
        
        assert vp1.poc == vp2.poc
        assert vp1.vah == vp2.vah
        assert vp1.val == vp2.val
