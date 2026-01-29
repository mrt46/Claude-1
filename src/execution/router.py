"""
Smart Order Router.

Determines optimal order type and execution strategy.
"""

from typing import Dict, Optional

from src.core.logger import get_logger

logger = get_logger(__name__)


class SmartOrderRouter:
    """
    Smart order router for optimal execution.
    
    Decision tree:
    - Order Size < $1000 → Market Order
    - Order Size $1000-$5000 & Good Liquidity → Limit Order
    - Order Size > $5000 & Good Liquidity → TWAP (split orders)
    - Poor Liquidity → REJECT
    """
    
    def __init__(
        self,
        small_order_threshold: float = 1000.0,
        large_order_threshold: float = 5000.0
    ):
        """
        Initialize order router.
        
        Args:
            small_order_threshold: Threshold for small orders (market)
            large_order_threshold: Threshold for large orders (TWAP)
        """
        self.small_order_threshold = small_order_threshold
        self.large_order_threshold = large_order_threshold
    
    def route_order(
        self,
        order_size_usdt: float,
        liquidity_quality: str,
        spread_quality: str
    ) -> Dict[str, any]:
        """
        Route order to optimal execution strategy.
        
        Args:
            order_size_usdt: Order size in USDT
            liquidity_quality: 'good', 'moderate', or 'poor'
            spread_quality: 'good', 'moderate', or 'poor'
        
        Returns:
            Dictionary with routing decision:
            {
                'order_type': 'market', 'limit', 'twap', or 'reject',
                'reason': str,
                'twap_splits': int (if TWAP)
            }
        """
        # Poor liquidity → reject
        if liquidity_quality == 'poor':
            return {
                'order_type': 'reject',
                'reason': 'Poor liquidity quality',
                'twap_splits': None
            }
        
        # Small orders → market
        if order_size_usdt < self.small_order_threshold:
            return {
                'order_type': 'market',
                'reason': f'Small order ({order_size_usdt:.2f} USDT < {self.small_order_threshold:.2f} USDT)',
                'twap_splits': None
            }
        
        # Medium orders with good liquidity → limit
        if order_size_usdt < self.large_order_threshold and liquidity_quality == 'good':
            return {
                'order_type': 'limit',
                'reason': f'Medium order with good liquidity',
                'twap_splits': None
            }
        
        # Large orders with good liquidity → TWAP
        if order_size_usdt >= self.large_order_threshold and liquidity_quality == 'good':
            # Split into 3-5 orders
            twap_splits = min(5, max(3, int(order_size_usdt / 2000)))
            return {
                'order_type': 'twap',
                'reason': f'Large order ({order_size_usdt:.2f} USDT), splitting into {twap_splits} orders',
                'twap_splits': twap_splits
            }
        
        # Default: limit order
        return {
            'order_type': 'limit',
            'reason': 'Default limit order',
            'twap_splits': None
        }
