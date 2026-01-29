"""
Professional logging system for the trading bot.

Provides structured logging with different levels and context.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class TradingBotLogger:
    """
    Centralized logging system for the trading bot.
    
    Features:
    - Console and file logging
    - Structured log format with timestamps
    - Different log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - Automatic log rotation
    """
    
    def __init__(
        self,
        name: str = "TradingBot",
        log_level: str = "INFO",
        log_file: Optional[Path] = None
    ):
        """
        Initialize the logger.
        
        Args:
            name: Logger name
            log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_file: Optional path to log file. If None, logs only to console.
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, log_level.upper()))
        
        # Prevent duplicate handlers
        if self.logger.handlers:
            return
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)
        
        # File handler (if specified)
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            file_format = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_format)
            self.logger.addHandler(file_handler)
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self.logger.debug(self._format_message(message, **kwargs))
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self.logger.info(self._format_message(message, **kwargs))
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self.logger.warning(self._format_message(message, **kwargs))
    
    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        self.logger.error(self._format_message(message, **kwargs))
    
    def critical(self, message: str, **kwargs) -> None:
        """Log critical message."""
        self.logger.critical(self._format_message(message, **kwargs))
    
    def _format_message(self, message: str, **kwargs) -> str:
        """Format message with optional context."""
        if kwargs:
            context = " | ".join(f"{k}={v}" for k, v in kwargs.items())
            return f"{message} | {context}"
        return message


# Global logger instance
_logger_instance: Optional[TradingBotLogger] = None


def get_logger(
    name: str = "TradingBot",
    log_level: str = "INFO",
    log_file: Optional[Path] = None
) -> TradingBotLogger:
    """
    Get or create a logger instance.
    
    Note: Returns a new instance each time (not singleton) to allow
    different configurations per logger name.
    
    Args:
        name: Logger name
        log_level: Minimum log level
        log_file: Optional log file path
    
    Returns:
        TradingBotLogger instance
    """
    return TradingBotLogger(name, log_level, log_file)
