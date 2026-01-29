"""
Dynamic position sizing based on risk management rules.
"""

from typing import Dict, Optional

from src.core.logger import get_logger

logger = get_logger(__name__)


class PositionSizer:
    """
    Calculates position size based on risk parameters.
    
    Formula:
    Risk Amount = Account Balance × Risk Per Trade %
    Risk Per Unit = |Entry Price - Stop Loss|
    Quantity = Risk Amount / Risk Per Unit
    """
    
    def __init__(
        self,
        risk_per_trade_percent: float = 2.0,
        max_position_size_usdt: float = 10000.0,
        min_position_size_usdt: float = 10.0
    ):
        """
        Initialize position sizer.
        
        Args:
            risk_per_trade_percent: Risk per trade as percentage of balance
            max_position_size_usdt: Maximum position size in USDT
            min_position_size_usdt: Minimum position size in USDT
        """
        self.risk_per_trade_percent = risk_per_trade_percent
        self.max_position_size_usdt = max_position_size_usdt
        self.min_position_size_usdt = min_position_size_usdt
    
    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss: float,
        side: str  # 'BUY' or 'SELL'
    ) -> Dict[str, float]:
        """
        Calculate position size.
        
        Args:
            account_balance: Account balance in USDT
            entry_price: Entry price
            stop_loss: Stop loss price
            side: 'BUY' or 'SELL'
        
        Returns:
            Dictionary with:
            {
                'quantity': float,
                'position_value_usdt': float,
                'risk_amount_usdt': float,
                'risk_per_unit': float,
                'risk_reward_ratio': float
            }
        """
        # Calculate risk per unit
        if side == 'BUY':
            risk_per_unit = entry_price - stop_loss
            if risk_per_unit <= 0:
                raise ValueError(f"Invalid stop loss for BUY: {stop_loss} >= {entry_price}")
        else:  # SELL
            risk_per_unit = stop_loss - entry_price
            if risk_per_unit <= 0:
                raise ValueError(f"Invalid stop loss for SELL: {stop_loss} <= {entry_price}")
        
        # Calculate risk amount
        risk_amount_usdt = account_balance * (self.risk_per_trade_percent / 100.0)
        
        # Calculate quantity
        quantity = risk_amount_usdt / risk_per_unit
        
        # Calculate position value
        position_value_usdt = quantity * entry_price
        
        # Apply limits
        if position_value_usdt > self.max_position_size_usdt:
            position_value_usdt = self.max_position_size_usdt
            quantity = position_value_usdt / entry_price
            risk_amount_usdt = quantity * risk_per_unit
        
        # Check minimum position size
        if position_value_usdt < self.min_position_size_usdt:
            # Try to increase to minimum
            min_quantity = self.min_position_size_usdt / entry_price
            if min_quantity * risk_per_unit <= account_balance * (self.risk_per_trade_percent / 100.0):
                quantity = min_quantity
                position_value_usdt = quantity * entry_price
                risk_amount_usdt = quantity * risk_per_unit
            else:
                raise ValueError(f"Position size too small: {position_value_usdt:.2f} USDT < {self.min_position_size_usdt:.2f} USDT")
        
        # Calculate risk/reward ratio (assuming take profit is 2x risk)
        take_profit_distance = risk_per_unit * 2
        risk_reward_ratio = take_profit_distance / risk_per_unit
        
        return {
            'quantity': quantity,
            'position_value_usdt': position_value_usdt,
            'risk_amount_usdt': risk_amount_usdt,
            'risk_per_unit': risk_per_unit,
            'risk_reward_ratio': risk_reward_ratio
        }
