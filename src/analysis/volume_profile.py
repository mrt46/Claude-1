"""
Volume Profile Analysis.

Calculates POC (Point of Control), VAH/VAL (Value Area), HVN/LVN (High/Low Volume Nodes).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import List, Optional

import numpy as np
import pandas as pd

from src.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class VolumeProfile:
    """Volume profile data structure."""
    price_levels: np.ndarray
    volumes: np.ndarray
    poc: float  # Point of Control
    vah: float  # Value Area High
    val: float  # Value Area Low
    hvn_levels: List[float]  # High Volume Nodes
    lvn_levels: List[float]  # Low Volume Nodes
    total_volume: float
    period_hours: int
    calculated_at: datetime


class VolumeProfileAnalyzer:
    """
    Professional volume profile analysis.
    
    Key concepts:
    - POC (Point of Control): Highest volume price level
    - VAH/VAL (Value Area High/Low): 70% volume range
    - HVN (High Volume Nodes): Strong support/resistance
    - LVN (Low Volume Nodes): Fast price movement areas
    """
    
    def __init__(self, num_bins: int = 100, value_area_percent: float = 0.70):
        """
        Initialize volume profile analyzer.
        
        Args:
            num_bins: Number of price bins for distribution
            value_area_percent: Percentage of volume for value area (default 70%)
        """
        self.num_bins = num_bins
        self.value_area_percent = value_area_percent
        self.cache: dict = {}
        self.cache_ttl = timedelta(minutes=5)
    
    def calculate_volume_profile(
        self,
        df: pd.DataFrame,
        period_hours: int = 24
    ) -> VolumeProfile:
        """
        Calculate volume profile for given period.
        
        Args:
            df: DataFrame with OHLCV data (must have columns: open, high, low, close, volume)
            period_hours: Period in hours to analyze
        
        Returns:
            VolumeProfile object
        
        Raises:
            ValueError: If insufficient data
        """
        # Check cache
        cache_key = f"{df['symbol'].iloc[0] if 'symbol' in df.columns else 'unknown'}_{period_hours}h"
        if cache_key in self.cache:
            cached_time, cached_vp = self.cache[cache_key]
            if datetime.now() - cached_time < self.cache_ttl:
                logger.debug(f"Using cached volume profile for {cache_key}")
                return cached_vp
        
        # Filter data by period
        if df.index.name == 'timestamp' or isinstance(df.index, pd.DatetimeIndex):
            cutoff_time = df.index[-1] - timedelta(hours=period_hours)
            df_period = df[df.index >= cutoff_time].copy()
        else:
            # If no timestamp index, use all data
            df_period = df.copy()
        
        if len(df_period) < 10:
            raise ValueError(f"Insufficient data: {len(df_period)} bars (minimum 10 required)")
        
        # Validate required columns
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df_period.columns:
                raise ValueError(f"Missing required column: {col}")
        
        # Create price bins
        price_min = float(df_period['low'].min())
        price_max = float(df_period['high'].max())
        
        if price_min >= price_max:
            raise ValueError("Invalid price range: min >= max")
        
        price_bins = np.linspace(price_min, price_max, self.num_bins + 1)
        
        # Distribute volume across price bins
        volume_distribution = np.zeros(self.num_bins)
        
        for _, row in df_period.iterrows():
            candle_low = float(row['low'])
            candle_high = float(row['high'])
            candle_volume = float(row['volume'])
            
            # Find bin indices
            candle_low_idx = np.digitize(candle_low, price_bins) - 1
            candle_high_idx = np.digitize(candle_high, price_bins) - 1
            
            # Clip to valid range
            candle_low_idx = max(0, min(candle_low_idx, self.num_bins - 1))
            candle_high_idx = max(0, min(candle_high_idx, self.num_bins - 1))
            
            # Distribute volume evenly across touched bins
            bins_touched = candle_high_idx - candle_low_idx + 1
            if bins_touched > 0:
                volume_per_bin = candle_volume / bins_touched
                
                for i in range(candle_low_idx, candle_high_idx + 1):
                    volume_distribution[i] += volume_per_bin
        
        # Calculate price level for each bin (midpoint)
        price_levels = (price_bins[:-1] + price_bins[1:]) / 2
        
        # Find POC (highest volume)
        poc_idx = np.argmax(volume_distribution)
        poc = float(price_levels[poc_idx])
        
        # Calculate Value Area (70% of volume)
        total_volume = float(volume_distribution.sum())
        
        if total_volume == 0:
            raise ValueError("Total volume is zero")
        
        target_va_volume = total_volume * self.value_area_percent
        
        # Sort bins by volume (descending)
        sorted_indices = np.argsort(volume_distribution)[::-1]
        
        va_indices = []
        cumulative_volume = 0.0
        
        for idx in sorted_indices:
            cumulative_volume += volume_distribution[idx]
            va_indices.append(int(idx))
            if cumulative_volume >= target_va_volume:
                break
        
        if not va_indices:
            raise ValueError("Could not calculate value area")
        
        vah = float(price_levels[max(va_indices)])
        val = float(price_levels[min(va_indices)])
        
        # Find HVN (High Volume Nodes) - top 10% volume
        hvn_threshold = np.percentile(volume_distribution, 90)
        hvn_indices = np.where(volume_distribution >= hvn_threshold)[0]
        hvn_levels = [float(price_levels[i]) for i in hvn_indices]
        
        # Find LVN (Low Volume Nodes) - bottom 10% volume
        lvn_threshold = np.percentile(volume_distribution, 10)
        lvn_indices = np.where(volume_distribution <= lvn_threshold)[0]
        lvn_levels = [float(price_levels[i]) for i in lvn_indices]
        
        # Create VolumeProfile object
        vp = VolumeProfile(
            price_levels=price_levels,
            volumes=volume_distribution,
            poc=poc,
            vah=vah,
            val=val,
            hvn_levels=hvn_levels,
            lvn_levels=lvn_levels,
            total_volume=total_volume,
            period_hours=period_hours,
            calculated_at=datetime.now()
        )
        
        # Cache result
        self.cache[cache_key] = (datetime.now(), vp)
        
        logger.debug(
            f"Volume profile calculated: POC={poc:.2f}, VAH={vah:.2f}, VAL={val:.2f}, "
            f"HVN={len(hvn_levels)}, LVN={len(lvn_levels)}"
        )
        
        return vp
    
    def get_current_position_in_profile(
        self,
        current_price: float,
        vp: VolumeProfile
    ) -> str:
        """
        Determine where current price is relative to value area.
        
        Args:
            current_price: Current market price
            vp: VolumeProfile object
        
        Returns:
            'above_vah', 'in_value_area', or 'below_val'
        """
        if current_price > vp.vah:
            return 'above_vah'
        elif current_price < vp.val:
            return 'below_val'
        else:
            return 'in_value_area'
    
    def find_nearest_hvn(
        self,
        price: float,
        vp: VolumeProfile,
        max_distance_percent: float = 0.02
    ) -> Optional[float]:
        """
        Find nearest HVN to given price.
        
        HVN acts as support/resistance.
        
        Args:
            price: Current price
            vp: VolumeProfile object
            max_distance_percent: Maximum distance as percentage (default 2%)
        
        Returns:
            Nearest HVN price or None if not found within range
        """
        if not vp.hvn_levels:
            return None
        
        nearest = min(vp.hvn_levels, key=lambda x: abs(x - price))
        distance = abs(nearest - price) / price
        
        if distance <= max_distance_percent:
            return nearest
        return None
    
    def find_nearest_lvn(
        self,
        price: float,
        vp: VolumeProfile,
        max_distance_percent: float = 0.02
    ) -> Optional[float]:
        """
        Find nearest LVN to given price.
        
        LVN indicates fast movement zones.
        
        Args:
            price: Current price
            vp: VolumeProfile object
            max_distance_percent: Maximum distance as percentage
        
        Returns:
            Nearest LVN price or None if not found within range
        """
        if not vp.lvn_levels:
            return None
        
        nearest = min(vp.lvn_levels, key=lambda x: abs(x - price))
        distance = abs(nearest - price) / price
        
        if distance <= max_distance_percent:
            return nearest
        return None
