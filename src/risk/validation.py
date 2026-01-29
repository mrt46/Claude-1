"""
Pre-trade validation and microstructure checks.
"""

from typing import Dict, Optional

from src.analysis.microstructure import MarketMicrostructure, OrderBook
from src.core.logger import get_logger

logger = get_logger(__name__)


class MicrostructureValidator:
    """
    Validates market microstructure before trade execution.
    
    Checks:
    - Spread quality
    - Liquidity depth
    - Slippage estimation
    """
    
    def __init__(self, max_slippage_percent: float = 0.5, min_liquidity_usdt: float = 50000.0):
        """
        Initialize validator.
        
        Args:
            max_slippage_percent: Maximum acceptable slippage
            min_liquidity_usdt: Minimum liquidity required
        """
        self.max_slippage_percent = max_slippage_percent
        self.min_liquidity_usdt = min_liquidity_usdt
        self.micro_analyzer = MarketMicrostructure()
    
    async def validate(
        self,
        order_book: OrderBook,
        order_size_usdt: float
    ) -> Dict[str, any]:
        """
        Validate microstructure for trade execution.
        
        Args:
            order_book: OrderBook object
            order_size_usdt: Order size in USDT
        
        Returns:
            Dictionary with validation results:
            {
                'valid': bool,
                'spread_quality': str,
                'liquidity_quality': str,
                'estimated_slippage': float,
                'reason': str (if invalid)
            }
        """
        try:
            # Analyze spread and liquidity
            micro = await self.micro_analyzer.analyze_spread_and_liquidity(order_book)
            
            # Check spread quality
            if micro['spread_quality'] == 'poor':
                return {
                    'valid': False,
                    'spread_quality': micro['spread_quality'],
                    'liquidity_quality': micro['liquidity_quality'],
                    'estimated_slippage': None,
                    'reason': f"Poor spread quality: {micro['spread_percent']:.3f}%"
                }
            
            # Check liquidity
            if micro['liquidity_usdt'] < self.min_liquidity_usdt:
                return {
                    'valid': False,
                    'spread_quality': micro['spread_quality'],
                    'liquidity_quality': micro['liquidity_quality'],
                    'estimated_slippage': None,
                    'reason': f"Insufficient liquidity: {micro['liquidity_usdt']:.0f} USDT < {self.min_liquidity_usdt:.0f} USDT"
                }
            
            # Estimate slippage
            buy_slippage = self.micro_analyzer.estimate_slippage(order_book, order_size_usdt, 'BUY')
            sell_slippage = self.micro_analyzer.estimate_slippage(order_book, order_size_usdt, 'SELL')
            
            max_slippage = max(
                abs(buy_slippage['slippage_percent']),
                abs(sell_slippage['slippage_percent'])
            )
            
            if max_slippage > self.max_slippage_percent:
                return {
                    'valid': False,
                    'spread_quality': micro['spread_quality'],
                    'liquidity_quality': micro['liquidity_quality'],
                    'estimated_slippage': max_slippage,
                    'reason': f"Excessive slippage: {max_slippage:.3f}% > {self.max_slippage_percent:.3f}%"
                }
            
            return {
                'valid': True,
                'spread_quality': micro['spread_quality'],
                'liquidity_quality': micro['liquidity_quality'],
                'estimated_slippage': max_slippage,
                'reason': None
            }
        
        except ValueError as e:
            # Re-raise ValueError (e.g., empty order book)
            raise
        except Exception as e:
            logger.error(f"Error validating microstructure: {e}")
            return {
                'valid': False,
                'spread_quality': 'unknown',
                'liquidity_quality': 'unknown',
                'estimated_slippage': None,
                'reason': f"Validation error: {str(e)}"
            }
