"""
Signal Deduplicator - Prevent duplicate signal execution.

Prevents opening duplicate positions from the same signal generated multiple times
by using signal fingerprinting with time-based caching.
"""

import time
from datetime import datetime
from typing import Dict

from src.core.logger import get_logger
from src.strategies.base import Signal

logger = get_logger(__name__)


class SignalDeduplicator:
    """
    Prevent duplicate signal execution.
    
    Uses signal fingerprinting to detect duplicate signals
    within a time window. This is critical for risk management
    as it prevents opening multiple positions from the same setup.
    
    Algorithm:
    1. Generate unique signal ID from: symbol, side, rounded price, time bucket
    2. Cache signal IDs with timestamps
    3. Check if signal ID exists in cache
    4. Clean expired entries (> TTL) before each check
    5. Reject duplicate signals within TTL window
    
    Example:
        Signal 1: BUY BTCUSDT @ 42150.75 at 17:03:22
        Signal 2: BUY BTCUSDT @ 42149.50 at 17:04:30
        
        Both round to 42151 (nearest dollar) and fall in 17:00-17:05 bucket
        → Same ID: "BTCUSDT_BUY_42151_17:00"
        → Signal 2 detected as duplicate!
    """
    
    def __init__(
        self,
        cache_ttl_seconds: int = 600,  # 10 minutes
        price_rounding_decimals: int = 0  # Round to nearest dollar
    ):
        """
        Initialize signal deduplicator.
        
        Args:
            cache_ttl_seconds: How long to remember signals (default: 600s = 10min).
                Signals older than this are considered expired and can be re-executed.
            price_rounding_decimals: Price rounding for fingerprint (default: 0 = nearest dollar).
                Higher values allow more price variation before detecting duplicates.
                
        Example:
            >>> deduplicator = SignalDeduplicator(
            ...     cache_ttl_seconds=600,  # 10 minutes
            ...     price_rounding_decimals=0  # Round to dollar
            ... )
        """
        if cache_ttl_seconds <= 0:
            raise ValueError(f"cache_ttl_seconds must be positive, got {cache_ttl_seconds}")
        if price_rounding_decimals < 0:
            raise ValueError(
                f"price_rounding_decimals must be non-negative, got {price_rounding_decimals}"
            )
        
        self.cache_ttl = cache_ttl_seconds
        self.price_rounding = price_rounding_decimals
        
        # Cache: {signal_id: timestamp}
        # timestamp is Unix time (seconds since epoch)
        self.signal_cache: Dict[str, float] = {}
        
        logger.info(
            f"SignalDeduplicator initialized: "
            f"ttl={cache_ttl_seconds}s ({cache_ttl_seconds/60:.1f}min), "
            f"price_rounding={price_rounding_decimals} decimals"
        )
    
    def generate_signal_id(self, signal: Signal) -> str:
        """
        Generate unique fingerprint for signal.
        
        Signal ID includes:
        - Symbol (e.g., "BTCUSDT")
        - Side (e.g., "BUY" or "SELL")
        - Entry price (rounded to avoid tiny differences)
        - Timestamp bucket (5-minute buckets: 00, 05, 10, 15, ...)
        
        Args:
            signal: Signal to fingerprint
            
        Returns:
            Signal ID string in format: "{SYMBOL}_{SIDE}_{PRICE}_{TIME_BUCKET}"
            
        Example:
            Signal: BUY BTCUSDT @ 42150.75 at 17:03:22
            - Rounded price: 42151 (nearest dollar)
            - Time bucket: 17:00 (5-minute bucket)
            - ID: "BTCUSDT_BUY_42151_17:00"
            
            Same signal at 17:04:30 would have same ID
            → Detected as duplicate!
            
        Raises:
            ValueError: If signal is invalid (missing required fields)
        """
        if not signal:
            raise ValueError("Signal cannot be None")
        
        if not signal.symbol:
            raise ValueError("Signal must have symbol")
        if not signal.side:
            raise ValueError("Signal must have side")
        if signal.entry_price is None:
            raise ValueError("Signal must have entry_price")
        if not signal.timestamp:
            raise ValueError("Signal must have timestamp")
        
        # Round price to avoid tiny differences causing false negatives
        rounded_price = round(signal.entry_price, self.price_rounding)
        
        # Timestamp bucket (5-minute buckets)
        # Examples: 17:03 → 17:00, 17:07 → 17:05, 17:12 → 17:10
        timestamp = signal.timestamp
        
        # Handle timezone-aware timestamps
        if timestamp.tzinfo is not None:
            # Convert to naive datetime for bucket calculation
            timestamp = timestamp.replace(tzinfo=None)
        
        bucket_minutes = (timestamp.minute // 5) * 5  # 0, 5, 10, 15, 20, ...
        time_bucket = timestamp.replace(
            minute=bucket_minutes,
            second=0,
            microsecond=0
        )
        
        # Generate ID
        # Format: "{SYMBOL}_{SIDE}_{PRICE}_{TIME_BUCKET}"
        signal_id = (
            f"{signal.symbol.upper()}_"
            f"{signal.side.upper()}_"
            f"{rounded_price:.{self.price_rounding}f}_"
            f"{time_bucket.strftime('%H:%M')}"
        )
        
        return signal_id
    
    def is_duplicate(self, signal: Signal) -> bool:
        """
        Check if signal is duplicate.
        
        Checks if a signal with the same fingerprint was seen recently
        (within cache TTL). Automatically cleans expired entries before checking.
        
        Args:
            signal: Signal to check
            
        Returns:
            True if duplicate (seen within TTL), False if new signal
            
        Example:
            >>> signal1 = Signal(...)  # BUY BTCUSDT @ 42150.75 at 17:03:22
            >>> signal2 = Signal(...)  # BUY BTCUSDT @ 42149.50 at 17:04:30
            >>> 
            >>> deduplicator.is_duplicate(signal1)  # False (new)
            >>> deduplicator.is_duplicate(signal2)  # True (duplicate!)
        """
        # Clean expired entries first
        self._clean_expired()
        
        # Generate ID
        try:
            signal_id = self.generate_signal_id(signal)
        except ValueError as e:
            logger.error(f"Failed to generate signal ID: {e}")
            # If we can't generate ID, treat as new signal (safer)
            return False
        
        # Check cache
        if signal_id in self.signal_cache:
            cached_time = self.signal_cache[signal_id]
            age_seconds = time.time() - cached_time
            
            logger.warning(
                f"⚠️ DUPLICATE SIGNAL DETECTED: {signal_id} "
                f"(first seen {age_seconds:.0f}s ago, "
                f"signal: {signal.symbol} {signal.side} @ {signal.entry_price:.2f})"
            )
            
            return True
        
        # New signal - add to cache
        self.signal_cache[signal_id] = time.time()
        
        logger.debug(
            f"New signal registered: {signal_id} "
            f"(signal: {signal.symbol} {signal.side} @ {signal.entry_price:.2f})"
        )
        
        return False
    
    def _clean_expired(self) -> None:
        """
        Remove expired entries from cache.
        
        Called automatically before each duplicate check to keep cache
        size manageable and ensure TTL is respected.
        
        Removes entries older than cache_ttl_seconds.
        """
        now = time.time()
        expired_ids = [
            signal_id
            for signal_id, timestamp in self.signal_cache.items()
            if now - timestamp > self.cache_ttl
        ]
        
        for signal_id in expired_ids:
            del self.signal_cache[signal_id]
        
        if expired_ids:
            logger.debug(
                f"Cleaned {len(expired_ids)} expired signal IDs from cache "
                f"(cache size: {len(self.signal_cache)})"
            )
    
    def register_execution(self, signal: Signal) -> None:
        """
        Register that signal was executed.
        
        Updates cache timestamp to prevent near-duplicates immediately
        after execution. This ensures that if a signal is executed,
        we don't immediately accept a duplicate signal in the next check.
        
        Args:
            signal: Signal that was executed
            
        Example:
            >>> signal = Signal(...)
            >>> deduplicator.is_duplicate(signal)  # False (new)
            >>> # ... execute signal ...
            >>> deduplicator.register_execution(signal)
            >>> # Now duplicate signals will be rejected for TTL duration
        """
        try:
            signal_id = self.generate_signal_id(signal)
            self.signal_cache[signal_id] = time.time()
            
            logger.debug(
                f"Signal execution registered: {signal_id} "
                f"(signal: {signal.symbol} {signal.side} @ {signal.entry_price:.2f})"
            )
        except ValueError as e:
            logger.error(f"Failed to register signal execution: {e}")
            # Don't raise - registration failure shouldn't break execution
    
    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with:
            - cache_size: Number of signals in cache
            - cache_ttl: TTL in seconds
        """
        return {
            'cache_size': len(self.signal_cache),
            'cache_ttl_seconds': self.cache_ttl
        }
    
    def clear_cache(self) -> None:
        """
        Clear all entries from cache.
        
        Useful for testing or resetting state.
        """
        cache_size = len(self.signal_cache)
        self.signal_cache.clear()
        logger.info(f"Cache cleared ({cache_size} entries removed)")
