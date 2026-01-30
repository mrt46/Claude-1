"""
API Rate Limiter - Prevent hitting exchange rate limits.

Implements token bucket algorithm for rate limiting API requests.
Binance limits:
- Spot API: 1200 requests/minute (weight-based)
- Order endpoints: 10 orders/second, 100,000 orders/day
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, Optional

from src.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_minute: int = 1200
    orders_per_second: int = 10
    orders_per_day: int = 100000
    burst_allowance: float = 0.8  # Use 80% of limit as safety margin


class RateLimiter:
    """
    Token bucket rate limiter for API requests.

    Features:
    - Separate limits for general requests and orders
    - Automatic request throttling
    - Weight-based limiting (Binance uses weights)
    - Burst protection
    - Daily order tracking
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        """
        Initialize rate limiter.

        Args:
            config: Rate limit configuration (default: Binance limits)
        """
        self.config = config or RateLimitConfig()

        # Apply safety margin
        self.max_requests_per_minute = int(
            self.config.requests_per_minute * self.config.burst_allowance
        )
        self.max_orders_per_second = int(
            self.config.orders_per_second * self.config.burst_allowance
        )
        self.max_orders_per_day = int(
            self.config.orders_per_day * self.config.burst_allowance
        )

        # Request tracking (sliding window)
        self._request_times: deque = deque()
        self._order_times: deque = deque()
        self._daily_order_count: int = 0
        self._daily_reset_time: float = time.time()

        # Weight tracking for Binance
        self._weight_window: deque = deque()  # (timestamp, weight)
        self._current_weight: int = 0
        self._max_weight_per_minute: int = 1200

        # Lock for thread safety
        self._lock = asyncio.Lock()

        logger.info(
            f"RateLimiter initialized: "
            f"max_requests={self.max_requests_per_minute}/min, "
            f"max_orders={self.max_orders_per_second}/sec, "
            f"max_daily_orders={self.max_orders_per_day}"
        )

    async def acquire(self, weight: int = 1, is_order: bool = False) -> bool:
        """
        Acquire permission to make an API request.

        Blocks if rate limit would be exceeded.

        Args:
            weight: Request weight (Binance assigns weights to endpoints)
            is_order: True if this is an order request (stricter limits)

        Returns:
            True if request is allowed
        """
        async with self._lock:
            now = time.time()

            # Clean old entries
            self._clean_old_entries(now)

            # Check daily order limit
            if is_order:
                self._check_daily_reset(now)
                if self._daily_order_count >= self.max_orders_per_day:
                    logger.error(
                        f"Daily order limit reached: {self._daily_order_count}/{self.max_orders_per_day}"
                    )
                    return False

            # Check weight limit
            if self._current_weight + weight > self._max_weight_per_minute:
                wait_time = self._calculate_wait_time(now)
                if wait_time > 0:
                    logger.warning(
                        f"Rate limit approaching, waiting {wait_time:.2f}s "
                        f"(weight: {self._current_weight}/{self._max_weight_per_minute})"
                    )
                    await asyncio.sleep(wait_time)
                    # Re-clean after waiting
                    now = time.time()
                    self._clean_old_entries(now)

            # Check order rate (per second)
            if is_order:
                recent_orders = sum(1 for t in self._order_times if now - t < 1.0)
                if recent_orders >= self.max_orders_per_second:
                    wait_time = 1.0 - (now - self._order_times[0]) if self._order_times else 1.0
                    logger.warning(f"Order rate limit, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                    now = time.time()

            # Record request
            self._request_times.append(now)
            self._weight_window.append((now, weight))
            self._current_weight += weight

            if is_order:
                self._order_times.append(now)
                self._daily_order_count += 1

            return True

    async def wait_if_needed(self, weight: int = 1, is_order: bool = False) -> None:
        """
        Wait if necessary before making a request.

        Similar to acquire() but doesn't return a value.

        Args:
            weight: Request weight
            is_order: True if order request
        """
        await self.acquire(weight, is_order)

    def _clean_old_entries(self, now: float) -> None:
        """Remove entries older than 1 minute."""
        cutoff = now - 60.0

        # Clean request times
        while self._request_times and self._request_times[0] < cutoff:
            self._request_times.popleft()

        # Clean order times (1 second window)
        order_cutoff = now - 1.0
        while self._order_times and self._order_times[0] < order_cutoff:
            self._order_times.popleft()

        # Clean weight window and recalculate
        while self._weight_window and self._weight_window[0][0] < cutoff:
            _, weight = self._weight_window.popleft()
            self._current_weight -= weight

        # Ensure weight doesn't go negative
        self._current_weight = max(0, self._current_weight)

    def _calculate_wait_time(self, now: float) -> float:
        """Calculate how long to wait before next request."""
        if not self._weight_window:
            return 0.0

        oldest_time = self._weight_window[0][0]
        # Wait until oldest entry expires
        wait_time = 60.0 - (now - oldest_time)
        return max(0.0, wait_time)

    def _check_daily_reset(self, now: float) -> None:
        """Reset daily counter if new day."""
        # Reset every 24 hours
        if now - self._daily_reset_time >= 86400:
            self._daily_order_count = 0
            self._daily_reset_time = now
            logger.info("Daily order counter reset")

    def get_stats(self) -> Dict:
        """
        Get current rate limiter statistics.

        Returns:
            Dictionary with current stats
        """
        now = time.time()
        self._clean_old_entries(now)

        return {
            'requests_last_minute': len(self._request_times),
            'current_weight': self._current_weight,
            'max_weight': self._max_weight_per_minute,
            'orders_last_second': len(self._order_times),
            'daily_orders': self._daily_order_count,
            'max_daily_orders': self.max_orders_per_day,
            'weight_utilization_percent': (
                self._current_weight / self._max_weight_per_minute * 100
            )
        }

    def is_rate_limited(self) -> bool:
        """
        Check if currently rate limited.

        Returns:
            True if at or near rate limit
        """
        stats = self.get_stats()
        return stats['weight_utilization_percent'] >= 90.0


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
