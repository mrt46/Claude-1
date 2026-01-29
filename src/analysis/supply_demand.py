"""
Supply and Demand Zone Detection.

Identifies areas where price consolidated before strong moves.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

import numpy as np
import pandas as pd

from src.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SupplyDemandZone:
    """Supply or demand zone."""
    zone_low: float
    zone_high: float
    zone_type: str  # 'demand' or 'supply'
    strength: float  # 0-1, based on volume and price movement
    is_fresh: bool  # True if not tested yet
    test_count: int  # Number of times price returned to zone
    created_at: datetime
    last_tested: Optional[datetime]


class SupplyDemandZones:
    """
    Supply and demand zone detector.
    
    Key concepts:
    - Demand Zone: Consolidation before rally (buy zone)
    - Supply Zone: Consolidation before drop (sell zone)
    - Fresh Zone: Not yet tested (stronger)
    - Tested Zone: Price returned to zone (weaker)
    """
    
    def __init__(
        self,
        min_consolidation_bars: int = 5,
        min_move_percent: float = 2.0
    ):
        """
        Initialize zone detector.
        
        Args:
            min_consolidation_bars: Minimum bars in consolidation
            min_move_percent: Minimum price move after consolidation (%)
        """
        self.min_consolidation_bars = min_consolidation_bars
        self.min_move_percent = min_move_percent
        self.zones: List[SupplyDemandZone] = []
    
    def find_demand_zones(
        self,
        df: pd.DataFrame,
        lookback_bars: int = 100
    ) -> List[SupplyDemandZone]:
        """
        Find demand zones (consolidation before rally).
        
        Args:
            df: DataFrame with OHLCV data
            lookback_bars: Number of bars to look back
        
        Returns:
            List of demand zones
        """
        if len(df) < lookback_bars:
            lookback_bars = len(df)
        
        df_recent = df.iloc[-lookback_bars:].copy()
        
        demand_zones = []
        
        # Look for consolidation followed by upward move
        for i in range(self.min_consolidation_bars, len(df_recent) - 5):
            # Check for consolidation
            consolidation_range = df_recent.iloc[i-self.min_consolidation_bars:i]
            
            consolidation_high = consolidation_range['high'].max()
            consolidation_low = consolidation_range['low'].min()
            consolidation_range_pct = ((consolidation_high - consolidation_low) / consolidation_low) * 100
            
            # Consolidation should be tight (< 1%)
            if consolidation_range_pct > 1.0:
                continue
            
            # Check for upward move after consolidation
            move_range = df_recent.iloc[i:i+5]
            move_high = move_range['high'].max()
            move_percent = ((move_high - consolidation_high) / consolidation_high) * 100
            
            if move_percent >= self.min_move_percent:
                # Found demand zone
                zone = SupplyDemandZone(
                    zone_low=float(consolidation_low),
                    zone_high=float(consolidation_high),
                    zone_type='demand',
                    strength=min(move_percent / 5.0, 1.0),  # Normalize to 0-1
                    is_fresh=True,
                    test_count=0,
                    created_at=consolidation_range.index[-1] if isinstance(consolidation_range.index, pd.DatetimeIndex) else datetime.now(),
                    last_tested=None
                )
                demand_zones.append(zone)
        
        # Remove overlapping zones (keep strongest)
        demand_zones = self._remove_overlapping_zones(demand_zones)
        
        logger.debug(f"Found {len(demand_zones)} demand zones")
        
        return demand_zones
    
    def find_supply_zones(
        self,
        df: pd.DataFrame,
        lookback_bars: int = 100
    ) -> List[SupplyDemandZone]:
        """
        Find supply zones (consolidation before drop).
        
        Args:
            df: DataFrame with OHLCV data
            lookback_bars: Number of bars to look back
        
        Returns:
            List of supply zones
        """
        if len(df) < lookback_bars:
            lookback_bars = len(df)
        
        df_recent = df.iloc[-lookback_bars:].copy()
        
        supply_zones = []
        
        # Look for consolidation followed by downward move
        for i in range(self.min_consolidation_bars, len(df_recent) - 5):
            # Check for consolidation
            consolidation_range = df_recent.iloc[i-self.min_consolidation_bars:i]
            
            consolidation_high = consolidation_range['high'].max()
            consolidation_low = consolidation_range['low'].min()
            consolidation_range_pct = ((consolidation_high - consolidation_low) / consolidation_low) * 100
            
            # Consolidation should be tight (< 1%)
            if consolidation_range_pct > 1.0:
                continue
            
            # Check for downward move after consolidation
            move_range = df_recent.iloc[i:i+5]
            move_low = move_range['low'].min()
            move_percent = ((consolidation_low - move_low) / consolidation_low) * 100
            
            if move_percent >= self.min_move_percent:
                # Found supply zone
                zone = SupplyDemandZone(
                    zone_low=float(consolidation_low),
                    zone_high=float(consolidation_high),
                    zone_type='supply',
                    strength=min(move_percent / 5.0, 1.0),  # Normalize to 0-1
                    is_fresh=True,
                    test_count=0,
                    created_at=consolidation_range.index[-1] if isinstance(consolidation_range.index, pd.DatetimeIndex) else datetime.now(),
                    last_tested=None
                )
                supply_zones.append(zone)
        
        # Remove overlapping zones (keep strongest)
        supply_zones = self._remove_overlapping_zones(supply_zones)
        
        logger.debug(f"Found {len(supply_zones)} supply zones")
        
        return supply_zones
    
    def update_zone_tests(
        self,
        zones: List[SupplyDemandZone],
        current_price: float
    ) -> List[SupplyDemandZone]:
        """
        Update zone test counts based on current price.
        
        Args:
            zones: List of zones
            current_price: Current market price
        
        Returns:
            Updated zones
        """
        for zone in zones:
            if zone.zone_low <= current_price <= zone.zone_high:
                # Price is in zone
                if zone.is_fresh:
                    zone.is_fresh = False
                zone.test_count += 1
                zone.last_tested = datetime.now()
                # Reduce strength with each test
                zone.strength *= 0.8
        
        return zones
    
    def _remove_overlapping_zones(
        self,
        zones: List[SupplyDemandZone]
    ) -> List[SupplyDemandZone]:
        """
        Remove overlapping zones, keeping the strongest.
        
        Args:
            zones: List of zones
        
        Returns:
            Non-overlapping zones
        """
        if not zones:
            return []
        
        # Sort by strength (descending)
        sorted_zones = sorted(zones, key=lambda z: z.strength, reverse=True)
        
        non_overlapping = []
        
        for zone in sorted_zones:
            overlaps = False
            
            for existing in non_overlapping:
                # Check if zones overlap
                if not (zone.zone_high < existing.zone_low or zone.zone_low > existing.zone_high):
                    overlaps = True
                    break
            
            if not overlaps:
                non_overlapping.append(zone)
        
        return non_overlapping
