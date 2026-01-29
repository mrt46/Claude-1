"""
Market Microstructure Analysis.

Analyzes spread, liquidity, and execution quality.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.analysis.orderbook import OrderBook, OrderBookAnalyzer

from src.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MicrostructureMetrics:
    """Market microstructure metrics."""
    spread_absolute: float  # bid-ask spread
    spread_percent: float  # spread as percentage
    spread_quality: str  # 'good', 'moderate', 'poor'
    liquidity_usdt: float
    liquidity_quality: str  # 'good', 'moderate', 'poor'
    best_bid: float
    best_ask: float
    mid_price: float


class MarketMicrostructure:
    """
    Market microstructure analyzer.
    
    Analyzes:
    - Spread (bid-ask difference)
    - Liquidity depth
    - Execution quality
    - Slippage estimation
    """
    
    def __init__(self):
        """Initialize microstructure analyzer."""
        self.ob_analyzer = OrderBookAnalyzer()
    
    async def analyze_spread_and_liquidity(
        self,
        ob: OrderBook
    ) -> Dict[str, Any]:
        """
        Analyze spread and liquidity from order book.
        
        Args:
            ob: OrderBook object
        
        Returns:
            Dictionary with microstructure metrics
        """
        if not ob.bids or not ob.asks:
            raise ValueError("Empty order book")
        
        best_bid = ob.bids[0][0]
        best_ask = ob.asks[0][0]
        
        spread_absolute = best_ask - best_bid
        spread_percent = (spread_absolute / best_bid) * 100 if best_bid > 0 else 0.0
        mid_price = (best_bid + best_ask) / 2
        
        # Assess spread quality
        if spread_percent < 0.05:
            spread_quality = 'good'
        elif spread_percent < 0.1:
            spread_quality = 'moderate'
        else:
            spread_quality = 'poor'
        
        # Calculate liquidity
        liquidity_usdt = self.ob_analyzer.calculate_liquidity(ob, depth_levels=20)
        liquidity_quality = self.ob_analyzer.assess_liquidity_quality(liquidity_usdt)
        
        return {
            'spread_absolute': spread_absolute,
            'spread_percent': spread_percent,
            'spread_quality': spread_quality,
            'liquidity_usdt': liquidity_usdt,
            'liquidity_quality': liquidity_quality,
            'best_bid': best_bid,
            'best_ask': best_ask,
            'mid_price': mid_price
        }
    
    def estimate_slippage(
        self,
        ob: OrderBook,
        order_size_usdt: float,
        side: str  # 'BUY' or 'SELL'
    ) -> Dict[str, float]:
        """
        Estimate slippage for a given order size.
        
        Args:
            ob: OrderBook object
            order_size_usdt: Order size in USDT
            side: 'BUY' or 'SELL'
        
        Returns:
            Dictionary with slippage estimates
        """
        if not ob.bids or not ob.asks:
            raise ValueError("Empty order book")
        
        if side == 'BUY':
            levels = ob.asks  # Buying from asks
            best_price = ob.asks[0][0]
        else:
            levels = ob.bids  # Selling to bids
            best_price = ob.bids[0][0]
        
        remaining_size = order_size_usdt
        total_cost = 0.0
        filled_quantity = 0.0
        
        for price, quantity in levels:
            level_value = price * quantity
            
            if remaining_size <= level_value:
                # Order fits in this level
                filled_quantity += remaining_size / price
                total_cost += remaining_size
                remaining_size = 0
                break
            else:
                # Consume entire level
                filled_quantity += quantity
                total_cost += level_value
                remaining_size -= level_value
        
        if remaining_size > 0:
            # Order too large, estimate worst case
            avg_price = total_cost / filled_quantity if filled_quantity > 0 else best_price
            worst_case_price = avg_price * 1.1  # Assume 10% worse
            total_cost += remaining_size * worst_case_price / best_price
            filled_quantity += remaining_size / worst_case_price
        
        avg_execution_price = total_cost / filled_quantity if filled_quantity > 0 else best_price
        slippage_absolute = avg_execution_price - best_price
        slippage_percent = (slippage_absolute / best_price) * 100 if best_price > 0 else 0.0
        
        return {
            'expected_price': avg_execution_price,
            'best_price': best_price,
            'slippage_absolute': slippage_absolute,
            'slippage_percent': slippage_percent,
            'filled_quantity': filled_quantity
        }
    
    def is_executable(
        self,
        ob: OrderBook,
        order_size_usdt: float,
        max_slippage_percent: float = 0.5
    ) -> bool:
        """
        Check if order is executable with acceptable slippage.
        
        Args:
            ob: OrderBook object
            order_size_usdt: Order size in USDT
            max_slippage_percent: Maximum acceptable slippage
        
        Returns:
            True if executable, False otherwise
        """
        try:
            # Estimate slippage for both sides
            buy_slippage = self.estimate_slippage(ob, order_size_usdt, 'BUY')
            sell_slippage = self.estimate_slippage(ob, order_size_usdt, 'SELL')
            
            max_slippage = max(
                abs(buy_slippage['slippage_percent']),
                abs(sell_slippage['slippage_percent'])
            )
            
            return max_slippage <= max_slippage_percent
        
        except Exception as e:
            logger.error(f"Error checking executability: {e}")
            return False
