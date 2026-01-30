"""
Configuration management for the trading bot.

Loads configuration from environment variables and provides type-safe access.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


def validate_api_key(key: str, name: str) -> None:
    """
    Validate API key format.

    Args:
        key: API key string
        name: Name of the key for error messages

    Raises:
        ConfigValidationError: If key format is invalid
    """
    if not key:
        raise ConfigValidationError(f"{name} is required")

    if len(key) < 20:
        raise ConfigValidationError(f"{name} appears too short (min 20 chars)")

    # Check for placeholder values
    placeholders = ['your_api_key', 'xxx', 'placeholder', 'test_key', '<api_key>']
    if key.lower() in placeholders:
        raise ConfigValidationError(f"{name} appears to be a placeholder value")


def validate_symbol(symbol: str) -> bool:
    """
    Validate trading symbol format.

    Args:
        symbol: Trading symbol (e.g., BTCUSDT)

    Returns:
        True if valid

    Raises:
        ConfigValidationError: If symbol format is invalid
    """
    # Basic format: uppercase letters only, 6-12 chars
    if not re.match(r'^[A-Z]{6,12}$', symbol):
        raise ConfigValidationError(
            f"Invalid symbol format: {symbol}. "
            f"Expected uppercase letters only (e.g., BTCUSDT)"
        )
    return True


def validate_percentage(value: float, name: str, min_val: float = 0.0, max_val: float = 100.0) -> None:
    """
    Validate percentage value.

    Args:
        value: Percentage value
        name: Parameter name for error messages
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Raises:
        ConfigValidationError: If value is out of range
    """
    if value < min_val or value > max_val:
        raise ConfigValidationError(
            f"{name} must be between {min_val} and {max_val}, got {value}"
        )


def validate_positive(value: float, name: str) -> None:
    """
    Validate that value is positive.

    Args:
        value: Numeric value
        name: Parameter name for error messages

    Raises:
        ConfigValidationError: If value is not positive
    """
    if value <= 0:
        raise ConfigValidationError(f"{name} must be positive, got {value}")


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
        # Top 5 liquid coins by volume (BTC, ETH, BNB, SOL, XRP)
        symbols_str = os.getenv("TRADING_SYMBOLS", "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT")
        self.trading = TradingConfig(
            symbols=[s.strip() for s in symbols_str.split(",")],
            base_currency=os.getenv("BASE_CURRENCY", "USDT"),
            quote_precision=int(os.getenv("QUOTE_PRECISION", "8")),
            min_order_size=float(os.getenv("MIN_ORDER_SIZE", "10.0")),
            max_order_size=float(os.getenv("MAX_ORDER_SIZE", "10000.0"))
        )

        # Validate all configuration
        self._validate()

    def _validate(self) -> None:
        """
        Validate all configuration values.

        Raises:
            ConfigValidationError: If any validation fails
        """
        errors = []

        # Validate API credentials
        try:
            validate_api_key(self.exchange.api_key, "BINANCE_API_KEY")
        except ConfigValidationError as e:
            errors.append(str(e))

        try:
            validate_api_key(self.exchange.api_secret, "BINANCE_API_SECRET")
        except ConfigValidationError as e:
            errors.append(str(e))

        # Validate symbols
        for symbol in self.trading.symbols:
            try:
                validate_symbol(symbol)
            except ConfigValidationError as e:
                errors.append(str(e))

        # Validate risk parameters
        try:
            validate_percentage(
                self.risk.max_daily_loss_percent,
                "MAX_DAILY_LOSS_PERCENT",
                0.1, 50.0
            )
        except ConfigValidationError as e:
            errors.append(str(e))

        try:
            validate_percentage(
                self.risk.max_drawdown_percent,
                "MAX_DRAWDOWN_PERCENT",
                1.0, 100.0
            )
        except ConfigValidationError as e:
            errors.append(str(e))

        try:
            validate_percentage(
                self.risk.risk_per_trade_percent,
                "RISK_PER_TRADE_PERCENT",
                0.1, 10.0
            )
        except ConfigValidationError as e:
            errors.append(str(e))

        try:
            validate_percentage(
                self.risk.max_slippage_percent,
                "MAX_SLIPPAGE_PERCENT",
                0.01, 5.0
            )
        except ConfigValidationError as e:
            errors.append(str(e))

        # Validate positive values
        try:
            validate_positive(self.risk.min_liquidity_usdt, "MIN_LIQUIDITY_USDT")
        except ConfigValidationError as e:
            errors.append(str(e))

        try:
            validate_positive(self.trading.min_order_size, "MIN_ORDER_SIZE")
        except ConfigValidationError as e:
            errors.append(str(e))

        # Validate max_positions
        if self.risk.max_positions < 1 or self.risk.max_positions > 50:
            errors.append(f"MAX_POSITIONS must be between 1 and 50, got {self.risk.max_positions}")

        # Validate order size range
        if self.trading.min_order_size >= self.trading.max_order_size:
            errors.append(
                f"MIN_ORDER_SIZE ({self.trading.min_order_size}) must be less than "
                f"MAX_ORDER_SIZE ({self.trading.max_order_size})"
            )

        # If any errors, raise with all messages
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            raise ConfigValidationError(error_msg)

    def print_summary(self) -> None:
        """Print configuration summary (hiding sensitive data)."""
        print("=" * 50)
        print("Configuration Summary")
        print("=" * 50)
        print(f"Exchange: {'TESTNET' if self.exchange.testnet else 'PRODUCTION'}")
        print(f"API Key: {self.exchange.api_key[:8]}...{self.exchange.api_key[-4:]}")
        print(f"Symbols: {', '.join(self.trading.symbols)}")
        print(f"Max Positions: {self.risk.max_positions}")
        print(f"Max Daily Loss: {self.risk.max_daily_loss_percent}%")
        print(f"Risk Per Trade: {self.risk.risk_per_trade_percent}%")
        print(f"Min Order Size: ${self.trading.min_order_size}")
        print(f"Max Order Size: ${self.trading.max_order_size}")
        print("=" * 50)
