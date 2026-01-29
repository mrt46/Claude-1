"""
Base Strategy Abstract Class.

All strategies must inherit from this class.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

from src.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Signal:
    """Trading signal."""
    strategy: str
    symbol: str
    side: str  # 'BUY' or 'SELL'
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float  # 0.0 to 1.0
    timestamp: datetime
    metadata: Dict[str, Any]


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    All strategies must implement:
    - generate_signal(): Returns Signal or None
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize strategy.
        
        Args:
            name: Strategy name
            config: Strategy configuration
        """
        self.name = name
        self.config = config
        self.logger = get_logger(f"Strategy.{name}")
    
    @abstractmethod
    async def generate_signal(
        self,
        df: pd.DataFrame,
        **kwargs
    ) -> Optional[Signal]:
        """
        Generate trading signal.
        
        Args:
            df: OHLCV DataFrame
            **kwargs: Additional data (order book, trades, etc.)
        
        Returns:
            Signal object or None if no signal
        """
        pass
    
    def validate_signal(self, signal: Signal) -> bool:
        """
        Validate signal before execution.
        
        Args:
            signal: Signal to validate
        
        Returns:
            True if valid, False otherwise
        """
        if signal.confidence < 0.0 or signal.confidence > 1.0:
            self.logger.warning(f"Invalid confidence: {signal.confidence}")
            return False
        
        if signal.entry_price <= 0:
            self.logger.warning(f"Invalid entry price: {signal.entry_price}")
            return False
        
        if signal.side == 'BUY':
            if signal.stop_loss >= signal.entry_price:
                self.logger.warning(f"Invalid stop loss for BUY: {signal.stop_loss} >= {signal.entry_price}")
                return False
            if signal.take_profit <= signal.entry_price:
                self.logger.warning(f"Invalid take profit for BUY: {signal.take_profit} <= {signal.entry_price}")
                return False
        else:  # SELL
            if signal.stop_loss <= signal.entry_price:
                self.logger.warning(f"Invalid stop loss for SELL: {signal.stop_loss} <= {signal.entry_price}")
                return False
            if signal.take_profit >= signal.entry_price:
                self.logger.warning(f"Invalid take profit for SELL: {signal.take_profit} >= {signal.entry_price}")
                return False
        
        return True
