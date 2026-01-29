"""
Order Book Analysis.

Analyzes order book depth, imbalance, walls, and liquidity.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

import numpy as np

from src.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OrderBook:
    """Order book data structure."""
    symbol: str
    bids: List[Tuple[float, float]]  # [(price, quantity), ...]
    asks: List[Tuple[float, float]]  # [(price, quantity), ...]
    timestamp: datetime


@dataclass
class OrderBookImbalance:
    """Order book imbalance metrics."""
    volume_imbalance: float  # bid_volume / ask_volume
    value_imbalance: float  # bid_value / ask_value
    spread_percent: float
    bid_volume: float
    ask_volume: float
    bid_value: float
    ask_value: float
    interpretation: str  # 'strong_buy_pressure', 'moderate_buy_pressure', etc.


@dataclass
class Wall:
    """Order book wall (large order)."""
    price: float
    quantity: float
    value: float  # price * quantity in USDT


@dataclass
class WallDetection:
    """Wall detection results."""
    bid_walls: List[Wall]
    ask_walls: List[Wall]
    nearest_bid_wall: Optional[Wall]
    nearest_ask_wall: Optional[Wall]
    avg_bid_size: float
    avg_ask_size: float


class OrderBookAnalyzer:
    """
    Real-time order book analysis.
    
    Key metrics:
    - Bid/Ask imbalance (who's stronger?)
    - Walls detection (whale orders)
    - Liquidity depth
    - Spread analysis
    """
    
    def __init__(self):
        """Initialize order book analyzer."""
        self.orderbook_cache: dict = {}
        self.update_frequency = 1.0  # Update every 1 second
    
    def calculate_imbalance(
        self,
        ob: OrderBook,
        depth_levels: int = 10
    ) -> OrderBookImbalance:
        """
        Calculate bid/ask imbalance.
        
        Imbalance > 1.5 → Strong buy pressure
        Imbalance < 0.67 → Strong sell pressure
        
        Args:
            ob: OrderBook object
            depth_levels: Number of levels to analyze
        
        Returns:
            OrderBookImbalance object
        """
        if not ob.bids or not ob.asks:
            raise ValueError("Empty order book")
        
        # Top N levels
        bids = ob.bids[:depth_levels]
        asks = ob.asks[:depth_levels]
        
        # Volume imbalance
        bid_volume = sum([qty for _, qty in bids])
        ask_volume = sum([qty for _, qty in asks])
        volume_imbalance = bid_volume / ask_volume if ask_volume > 0 else 0.0
        
        # Value imbalance (price * quantity)
        bid_value = sum([price * qty for price, qty in bids])
        ask_value = sum([price * qty for price, qty in asks])
        value_imbalance = bid_value / ask_value if ask_value > 0 else 0.0
        
        # Spread
        best_bid = bids[0][0]
        best_ask = asks[0][0]
        spread = ((best_ask - best_bid) / best_bid) * 100 if best_bid > 0 else 0.0
        
        # Interpretation
        if volume_imbalance > 1.5:
            interpretation = 'strong_buy_pressure'
        elif volume_imbalance > 1.2:
            interpretation = 'moderate_buy_pressure'
        elif volume_imbalance < 0.67:
            interpretation = 'strong_sell_pressure'
        elif volume_imbalance < 0.83:
            interpretation = 'moderate_sell_pressure'
        else:
            interpretation = 'balanced'
        
        return OrderBookImbalance(
            volume_imbalance=volume_imbalance,
            value_imbalance=value_imbalance,
            spread_percent=spread,
            bid_volume=bid_volume,
            ask_volume=ask_volume,
            bid_value=bid_value,
            ask_value=ask_value,
            interpretation=interpretation
        )
    
    def detect_walls(
        self,
        ob: OrderBook,
        threshold_multiplier: float = 3.0
    ) -> WallDetection:
        """
        Detect abnormally large orders (walls).
        
        Walls can act as:
        - Support (bid walls)
        - Resistance (ask walls)
        - Fake walls (pulled before hit)
        
        Args:
            ob: OrderBook object
            threshold_multiplier: Multiplier for average size to consider a wall
        
        Returns:
            WallDetection object
        """
        if not ob.bids or not ob.asks:
            raise ValueError("Empty order book")
        
        # Analyze top 50 levels
        all_bids = ob.bids[:50]
        all_asks = ob.asks[:50]
        
        if not all_bids or not all_asks:
            return WallDetection(
                bid_walls=[],
                ask_walls=[],
                nearest_bid_wall=None,
                nearest_ask_wall=None,
                avg_bid_size=0.0,
                avg_ask_size=0.0
            )
        
        # Calculate average order size
        bid_sizes = [qty for _, qty in all_bids]
        ask_sizes = [qty for _, qty in all_asks]
        
        avg_bid_size = np.mean(bid_sizes) if bid_sizes else 0.0
        avg_ask_size = np.mean(ask_sizes) if ask_sizes else 0.0
        
        # Find walls (orders > threshold * average)
        bid_walls = []
        for price, qty in all_bids:
            if qty > avg_bid_size * threshold_multiplier:
                bid_walls.append(Wall(
                    price=price,
                    quantity=qty,
                    value=price * qty
                ))
        
        ask_walls = []
        for price, qty in all_asks:
            if qty > avg_ask_size * threshold_multiplier:
                ask_walls.append(Wall(
                    price=price,
                    quantity=qty,
                    value=price * qty
                ))
        
        # Sort walls by price (bids descending, asks ascending)
        bid_walls.sort(key=lambda w: w.price, reverse=True)
        ask_walls.sort(key=lambda w: w.price)
        
        return WallDetection(
            bid_walls=bid_walls,
            ask_walls=ask_walls,
            nearest_bid_wall=bid_walls[0] if bid_walls else None,
            nearest_ask_wall=ask_walls[0] if ask_walls else None,
            avg_bid_size=avg_bid_size,
            avg_ask_size=avg_ask_size
        )
    
    def calculate_liquidity(
        self,
        ob: OrderBook,
        depth_levels: int = 20
    ) -> float:
        """
        Calculate total liquidity in USDT.
        
        >100k USDT → Good liquidity
        <10k USDT → Poor liquidity (avoid trading)
        
        Args:
            ob: OrderBook object
            depth_levels: Number of levels to analyze
        
        Returns:
            Total liquidity in USDT
        """
        if not ob.bids or not ob.asks:
            return 0.0
        
        bids = ob.bids[:depth_levels]
        asks = ob.asks[:depth_levels]
        
        bid_liquidity = sum([price * qty for price, qty in bids])
        ask_liquidity = sum([price * qty for price, qty in asks])
        
        return bid_liquidity + ask_liquidity
    
    def assess_liquidity_quality(
        self,
        liquidity_usdt: float
    ) -> str:
        """
        Assess liquidity quality.
        
        Args:
            liquidity_usdt: Total liquidity in USDT
        
        Returns:
            'good', 'moderate', or 'poor'
        """
        if liquidity_usdt >= 100000:
            return 'good'
        elif liquidity_usdt >= 50000:
            return 'moderate'
        else:
            return 'poor'
