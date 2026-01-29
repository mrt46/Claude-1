"""
Cumulative Volume Delta (CVD) Analysis.

Tracks buy vs sell volume and detects divergences with price.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd

from src.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CVDData:
    """CVD data structure."""
    timestamps: List[datetime]
    prices: List[float]
    cvd_values: List[float]  # Cumulative volume delta
    buy_volume: List[float]
    sell_volume: List[float]
    delta: List[float]  # Buy volume - Sell volume per trade


class VolumeDeltaAnalyzer:
    """
    Cumulative Volume Delta (CVD) analyzer.
    
    CVD = Cumulative sum of (Buy Volume - Sell Volume)
    
    Key concepts:
    - Positive CVD: More buying pressure
    - Negative CVD: More selling pressure
    - Divergence: Price moves one way, CVD moves opposite (reversal signal)
    """
    
    def __init__(self):
        """Initialize CVD analyzer."""
        pass
    
    def calculate_cvd_from_trades(
        self,
        trades_df: pd.DataFrame
    ) -> CVDData:
        """
        Calculate CVD from trade data.
        
        Args:
            trades_df: DataFrame with columns: timestamp, price, quantity, is_buyer_maker
        
        Returns:
            CVDData object
        """
        if trades_df.empty:
            raise ValueError("Empty trades DataFrame")
        
        required_cols = ['price', 'quantity', 'is_buyer_maker']
        for col in required_cols:
            if col not in trades_df.columns:
                raise ValueError(f"Missing required column: {col}")
        
        # Sort by timestamp
        df = trades_df.sort_index() if isinstance(trades_df.index, pd.DatetimeIndex) else trades_df
        
        timestamps = []
        prices = []
        buy_volumes = []
        sell_volumes = []
        deltas = []
        cvd_values = []
        
        cumulative_delta = 0.0
        
        for idx, row in df.iterrows():
            timestamp = idx if isinstance(idx, datetime) else row.get('timestamp', datetime.now())
            price = float(row['price'])
            quantity = float(row['quantity'])
            is_buyer_maker = bool(row['is_buyer_maker'])
            
            # If buyer is maker, it's a sell order (market sell)
            # If buyer is taker, it's a buy order (market buy)
            if is_buyer_maker:
                # Sell order
                sell_volumes.append(quantity)
                buy_volumes.append(0.0)
                delta = -quantity
            else:
                # Buy order
                buy_volumes.append(quantity)
                sell_volumes.append(0.0)
                delta = quantity
            
            cumulative_delta += delta
            
            timestamps.append(timestamp)
            prices.append(price)
            deltas.append(delta)
            cvd_values.append(cumulative_delta)
        
        return CVDData(
            timestamps=timestamps,
            prices=prices,
            cvd_values=cvd_values,
            buy_volume=buy_volumes,
            sell_volume=sell_volumes,
            delta=deltas
        )
    
    def calculate_cvd_divergence(
        self,
        price_df: pd.DataFrame,
        cvd_data: CVDData,
        lookback_periods: int = 20
    ) -> Optional[str]:
        """
        Detect CVD divergence with price.
        
        Divergence types:
        - Bullish divergence: Price makes lower low, CVD makes higher low
        - Bearish divergence: Price makes higher high, CVD makes lower high
        
        Args:
            price_df: DataFrame with price data (must have 'close' column)
            cvd_data: CVDData object
            lookback_periods: Number of periods to look back
        
        Returns:
            'bullish_divergence', 'bearish_divergence', or None
        """
        if len(cvd_data.prices) < lookback_periods:
            return None
        
        # Get recent data
        recent_prices = price_df['close'].iloc[-lookback_periods:].values
        recent_cvd = np.array(cvd_data.cvd_values[-lookback_periods:])
        
        if len(recent_prices) != len(recent_cvd):
            # Align by taking minimum length
            min_len = min(len(recent_prices), len(recent_cvd))
            recent_prices = recent_prices[-min_len:]
            recent_cvd = recent_cvd[-min_len:]
        
        if len(recent_prices) < 5:
            return None
        
        # Calculate price and CVD trends
        price_trend = recent_prices[-1] - recent_prices[0]
        cvd_trend = recent_cvd[-1] - recent_cvd[0]
        
        # Normalize trends
        price_volatility = np.std(recent_prices)
        cvd_volatility = np.std(recent_cvd)
        
        if price_volatility == 0 or cvd_volatility == 0:
            return None
        
        normalized_price_trend = price_trend / price_volatility
        normalized_cvd_trend = cvd_trend / cvd_volatility
        
        # Detect divergence
        # Bullish divergence: Price down, CVD up
        if normalized_price_trend < -0.5 and normalized_cvd_trend > 0.5:
            logger.debug("Bullish divergence detected: Price down, CVD up")
            return 'bullish_divergence'
        
        # Bearish divergence: Price up, CVD down
        if normalized_price_trend > 0.5 and normalized_cvd_trend < -0.5:
            logger.debug("Bearish divergence detected: Price up, CVD down")
            return 'bearish_divergence'
        
        return None
    
    def get_cvd_trend(
        self,
        cvd_data: CVDData,
        lookback_periods: int = 10
    ) -> str:
        """
        Get current CVD trend.
        
        Args:
            cvd_data: CVDData object
            lookback_periods: Number of periods to analyze
        
        Returns:
            'bullish', 'bearish', or 'neutral'
        """
        if len(cvd_data.cvd_values) < lookback_periods:
            return 'neutral'
        
        recent_cvd = cvd_data.cvd_values[-lookback_periods:]
        
        if recent_cvd[-1] > recent_cvd[0] * 1.1:
            return 'bullish'
        elif recent_cvd[-1] < recent_cvd[0] * 0.9:
            return 'bearish'
        else:
            return 'neutral'
