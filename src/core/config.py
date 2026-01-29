"""
Configuration management for the trading bot.

Loads configuration from environment variables and provides type-safe access.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv


@dataclass
class DatabaseConfig:
    """Database configuration."""
    timescaledb_host: str
    timescaledb_port: int
    timescaledb_database: str
    timescaledb_user: str
    timescaledb_password: str
    redis_host: str
    redis_port: int
    redis_password: Optional[str] = None
    redis_db: int = 0


@dataclass
class ExchangeConfig:
    """Exchange API configuration."""
    api_key: str
    api_secret: str
    testnet: bool = False
    base_url: Optional[str] = None


@dataclass
class StrategyConfig:
    """Strategy configuration."""
    min_score: float = 7.0
    min_buy_score: float = None
    min_sell_score: float = None
    weights: Dict[str, float] = None
    
    def __post_init__(self):
        """Set default weights if not provided."""
        if self.weights is None:
            self.weights = {
                'volume_profile': 2.0,
                'orderbook': 2.0,
                'cvd': 2.0,
                'supply_demand': 2.0,
                'hvn_support': 1.0,
                'time_of_day': 1.0
            }
        # Set default buy/sell scores if not provided
        if self.min_buy_score is None:
            self.min_buy_score = self.min_score
        if self.min_sell_score is None:
            self.min_sell_score = self.min_score


@dataclass
class RiskConfig:
    """Risk management configuration."""
    max_positions: int = 5
    max_daily_loss_percent: float = 5.0
    max_drawdown_percent: float = 15.0
    max_symbol_exposure_percent: float = 20.0
    risk_per_trade_percent: float = 2.0
    max_slippage_percent: float = 0.5
    min_liquidity_usdt: float = 50000.0
    min_usdt_reserve: float = 10.0  # Minimum USDT to keep for BNB purchases


@dataclass
class TradingConfig:
    """Trading configuration."""
    symbols: List[str]
    base_currency: str = "USDT"
    quote_precision: int = 8
    min_order_size: float = 10.0
    max_order_size: float = 10000.0


class Config:
    """
    Central configuration manager.
    
    Loads configuration from environment variables with sensible defaults.
    """
    
    def __init__(self, env_file: Optional[Path] = None):
        """
        Initialize configuration.
        
        Args:
            env_file: Optional path to .env file. If None, looks for .env in project root.
        """
        if env_file is None:
            env_file = Path(__file__).parent.parent.parent / ".env"
        
        load_dotenv(env_file)
        
        # Database config
        self.database = DatabaseConfig(
            timescaledb_host=os.getenv("TIMESCALEDB_HOST", "localhost"),
            timescaledb_port=int(os.getenv("TIMESCALEDB_PORT", "5432")),
            timescaledb_database=os.getenv("TIMESCALEDB_DATABASE", "trading_bot"),
            timescaledb_user=os.getenv("TIMESCALEDB_USER", "postgres"),
            timescaledb_password=os.getenv("TIMESCALEDB_PASSWORD", ""),
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_password=os.getenv("REDIS_PASSWORD"),
            redis_db=int(os.getenv("REDIS_DB", "0"))
        )
        
        # Exchange config
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        
        if not api_key or not api_secret:
            raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET must be set")
        
        self.exchange = ExchangeConfig(
            api_key=api_key,
            api_secret=api_secret,
            testnet=os.getenv("BINANCE_TESTNET", "false").lower() == "true",
            base_url=os.getenv("BINANCE_BASE_URL")
        )
        
        # Strategy config
        min_score = float(os.getenv("STRATEGY_MIN_SCORE", "7.0"))
        min_buy_score = float(os.getenv("STRATEGY_MIN_BUY_SCORE", str(min_score)))
        min_sell_score = float(os.getenv("STRATEGY_MIN_SELL_SCORE", str(min_score)))
        
        self.strategy = StrategyConfig(
            min_score=min_score,
            min_buy_score=min_buy_score,
            min_sell_score=min_sell_score,
            weights={
                'volume_profile': float(os.getenv("WEIGHT_VOLUME_PROFILE", "2.0")),
                'orderbook': float(os.getenv("WEIGHT_ORDERBOOK", "2.0")),
                'cvd': float(os.getenv("WEIGHT_CVD", "2.0")),
                'supply_demand': float(os.getenv("WEIGHT_SUPPLY_DEMAND", "2.0")),
                'hvn_support': float(os.getenv("WEIGHT_HVN", "1.0")),
                'time_of_day': float(os.getenv("WEIGHT_TIME_OF_DAY", "1.0"))
            }
        )
        
        # Risk config
        self.risk = RiskConfig(
            max_positions=int(os.getenv("MAX_POSITIONS", "5")),
            max_daily_loss_percent=float(os.getenv("MAX_DAILY_LOSS_PERCENT", "5.0")),
            max_drawdown_percent=float(os.getenv("MAX_DRAWDOWN_PERCENT", "15.0")),
            max_symbol_exposure_percent=float(os.getenv("MAX_SYMBOL_EXPOSURE_PERCENT", "20.0")),
            risk_per_trade_percent=float(os.getenv("RISK_PER_TRADE_PERCENT", "2.0")),
            max_slippage_percent=float(os.getenv("MAX_SLIPPAGE_PERCENT", "0.5")),
            min_liquidity_usdt=float(os.getenv("MIN_LIQUIDITY_USDT", "50000.0")),
            min_usdt_reserve=float(os.getenv("MIN_USDT_RESERVE", "10.0"))
        )
        
        # Trading config
        symbols_str = os.getenv("TRADING_SYMBOLS", "BTCUSDT,ETHUSDT")
        self.trading = TradingConfig(
            symbols=[s.strip() for s in symbols_str.split(",")],
            base_currency=os.getenv("BASE_CURRENCY", "USDT"),
            quote_precision=int(os.getenv("QUOTE_PRECISION", "8")),
            min_order_size=float(os.getenv("MIN_ORDER_SIZE", "10.0")),
            max_order_size=float(os.getenv("MAX_ORDER_SIZE", "10000.0"))
        )
