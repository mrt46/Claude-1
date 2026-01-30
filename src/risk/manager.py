"""
Central risk management controller.

Pre-trade validation and portfolio risk checks.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.analysis.microstructure import OrderBook
from src.core.logger import get_logger
from src.risk.sizing import PositionSizer
from src.risk.validation import MicrostructureValidator
from src.strategies.base import Signal

logger = get_logger(__name__)


class RiskManager:
    """
    Central risk management controller.
    
    Pre-trade checks:
    1. Microstructure quality
    2. Slippage estimation
    3. Portfolio limits
    4. Position sizing
    """
    
    def __init__(
        self,
        max_positions: int = 5,
        max_daily_loss_percent: float = 5.0,
        max_drawdown_percent: float = 15.0,
        max_symbol_exposure_percent: float = 20.0,
        risk_per_trade_percent: float = 2.0,
        max_slippage_percent: float = 0.5,
        min_liquidity_usdt: float = 50000.0,
        min_usdt_reserve: float = 10.0
    ):
        """
        Initialize risk manager.
        
        Args:
            max_positions: Maximum number of open positions
            max_daily_loss_percent: Maximum daily loss percentage
            max_drawdown_percent: Maximum drawdown percentage
            max_symbol_exposure_percent: Maximum exposure per symbol
            risk_per_trade_percent: Risk per trade percentage
            max_slippage_percent: Maximum acceptable slippage
            min_liquidity_usdt: Minimum liquidity required
        """
        self.max_positions = max_positions
        self.max_daily_loss_percent = max_daily_loss_percent
        self.max_drawdown_percent = max_drawdown_percent
        self.max_symbol_exposure_percent = max_symbol_exposure_percent
        self.max_slippage_percent = max_slippage_percent
        self.min_liquidity_usdt = min_liquidity_usdt
        self.min_usdt_reserve = min_usdt_reserve  # Minimum USDT to keep for BNB
        
        # Initialize validators and sizers
        self.validator = MicrostructureValidator(
            max_slippage_percent=max_slippage_percent,
            min_liquidity_usdt=min_liquidity_usdt
        )
        self.sizer = PositionSizer(risk_per_trade_percent=risk_per_trade_percent)
        
        # Portfolio state
        self.open_positions: List[Dict] = []
        self.daily_pnl: float = 0.0
        self.daily_start_balance: float = 0.0
        self.max_balance: float = 0.0
    
    def set_daily_start_balance(self, balance: float) -> None:
        """Set starting balance for the day."""
        self.daily_start_balance = balance
        self.max_balance = balance
        self.daily_pnl = 0.0
        logger.info(f"Daily start balance set: {balance:.2f} USDT")
    
    def update_daily_pnl(self, current_balance: float) -> None:
        """Update daily PnL and max balance."""
        self.daily_pnl = current_balance - self.daily_start_balance
        if current_balance > self.max_balance:
            self.max_balance = current_balance
    
    def add_position(self, position: Dict) -> None:
        """Add open position."""
        self.open_positions.append(position)
        logger.info(f"Position added: {position.get('symbol')} {position.get('side')} @ {position.get('entry_price')}")
    
    def remove_position(self, position_id: str) -> None:
        """Remove closed position."""
        self.open_positions = [p for p in self.open_positions if p.get('id') != position_id]
    
    async def validate_trade(
        self,
        signal: Signal,
        account_balance: float,
        order_book: OrderBook
    ) -> Dict[str, Any]:
        """
        Validate trade before execution.
        
        Args:
            signal: Trading signal
            account_balance: Current account balance
            order_book: Order book for microstructure check
        
        Returns:
            Dictionary with validation results:
            {
                'approved': bool,
                'position_size': dict (if approved),
                'reason': str (if rejected)
            }
        """
        # Check 1: Microstructure quality
        try:
            # Estimate order size first (rough estimate)
            estimated_size = account_balance * (self.sizer.risk_per_trade_percent / 100.0)
            
            micro_validation = await self.validator.validate(order_book, estimated_size)
            
            if not micro_validation['valid']:
                return {
                    'approved': False,
                    'position_size': None,
                    'reason': f"Microstructure validation failed: {micro_validation['reason']}"
                }
        except Exception as e:
            logger.error(f"Microstructure validation error: {e}")
            return {
                'approved': False,
                'position_size': None,
                'reason': f"Microstructure validation error: {str(e)}"
            }
        
        # Check 2: Portfolio limits
        if len(self.open_positions) >= self.max_positions:
            return {
                'approved': False,
                'position_size': None,
                'reason': f"Maximum positions reached: {len(self.open_positions)}/{self.max_positions}"
            }
        
        # Check 3: Daily loss limit
        daily_loss_percent = (self.daily_pnl / self.daily_start_balance) * 100 if self.daily_start_balance > 0 else 0.0
        if daily_loss_percent <= -self.max_daily_loss_percent:
            return {
                'approved': False,
                'position_size': None,
                'reason': f"Daily loss limit reached: {daily_loss_percent:.2f}% <= -{self.max_daily_loss_percent}%"
            }
        
        # Check 4: Drawdown limit
        drawdown = ((self.max_balance - account_balance) / self.max_balance) * 100 if self.max_balance > 0 else 0.0
        if drawdown >= self.max_drawdown_percent:
            return {
                'approved': False,
                'position_size': None,
                'reason': f"Maximum drawdown reached: {drawdown:.2f}% >= {self.max_drawdown_percent}%"
            }
        
        # Check 5: Symbol exposure
        symbol_positions = [p for p in self.open_positions if p.get('symbol') == signal.symbol]
        symbol_exposure = sum([p.get('position_value_usdt', 0) for p in symbol_positions])
        symbol_exposure_percent = (symbol_exposure / account_balance) * 100 if account_balance > 0 else 0.0
        
        if symbol_exposure_percent >= self.max_symbol_exposure_percent:
            return {
                'approved': False,
                'position_size': None,
                'reason': f"Symbol exposure limit reached: {symbol_exposure_percent:.2f}% >= {self.max_symbol_exposure_percent}%"
            }
        
        # Check 6: Position sizing
        try:
            position_size = self.sizer.calculate_position_size(
                account_balance=account_balance,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                side=signal.side
            )
        except Exception as e:
            return {
                'approved': False,
                'position_size': None,
                'reason': f"Position sizing failed: {str(e)}"
            }
        
        # Check 7: Minimum USDT reserve (for BNB purchases)
        remaining_usdt = account_balance - position_size['position_value_usdt']
        if remaining_usdt < self.min_usdt_reserve:
            return {
                'approved': False,
                'position_size': None,
                'reason': f"Insufficient USDT reserve: Need {self.min_usdt_reserve} USDT for BNB, "
                          f"available after trade: {remaining_usdt:.2f} USDT"
            }
        
        # Final check: Verify slippage with actual position size
        final_slippage_check = await self.validator.validate(
            order_book,
            position_size['position_value_usdt']
        )
        
        if not final_slippage_check['valid']:
            return {
                'approved': False,
                'position_size': None,
                'reason': f"Final slippage check failed: {final_slippage_check['reason']}"
            }
        
        logger.info(
            f"Trade approved: {signal.symbol} {signal.side} @ {signal.entry_price:.2f}, "
            f"size={position_size['position_value_usdt']:.2f} USDT, "
            f"risk={position_size['risk_amount_usdt']:.2f} USDT"
        )
        
        return {
            'approved': True,
            'position_size': position_size,
            'reason': None
        }
