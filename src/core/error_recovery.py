"""
Error Recovery - Retry logic and circuit breaker patterns.

Provides robust error handling for API calls and critical operations.
"""

import asyncio
import functools
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, Union

from src.core.logger import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple = (Exception,)
    non_retryable_exceptions: tuple = ()


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5  # Failures before opening
    recovery_timeout: float = 60.0  # Seconds before half-open
    success_threshold: int = 2  # Successes before closing


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.

    Prevents cascading failures by stopping calls to failing services.

    States:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Service failing, calls rejected immediately
    - HALF_OPEN: Testing if service recovered
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Circuit breaker name (for logging)
            config: Configuration options
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None

        logger.info(f"CircuitBreaker '{name}' initialized")

    @property
    def state(self) -> CircuitState:
        """Get current state (may transition based on time)."""
        if self._state == CircuitState.OPEN:
            # Check if recovery timeout passed
            if self._last_failure_time:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.config.recovery_timeout:
                    logger.info(
                        f"CircuitBreaker '{self.name}': OPEN -> HALF_OPEN "
                        f"(recovery timeout elapsed)"
                    )
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0

        return self._state

    def is_available(self) -> bool:
        """Check if calls can be made."""
        return self.state != CircuitState.OPEN

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.config.success_threshold:
                logger.info(
                    f"CircuitBreaker '{self.name}': HALF_OPEN -> CLOSED "
                    f"(success threshold reached)"
                )
                self._state = CircuitState.CLOSED
                self._failure_count = 0

        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            # Any failure in half-open goes back to open
            logger.warning(
                f"CircuitBreaker '{self.name}': HALF_OPEN -> OPEN "
                f"(failure during recovery)"
            )
            self._state = CircuitState.OPEN
            self._success_count = 0

        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.config.failure_threshold:
                logger.warning(
                    f"CircuitBreaker '{self.name}': CLOSED -> OPEN "
                    f"(failure threshold {self._failure_count} reached)"
                )
                self._state = CircuitState.OPEN

    def get_stats(self) -> Dict:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure": self._last_failure_time
        }


class RetryHandler:
    """
    Retry handler with exponential backoff.

    Features:
    - Exponential backoff with jitter
    - Configurable retry exceptions
    - Maximum retry limit
    - Logging of retry attempts
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        """
        Initialize retry handler.

        Args:
            config: Retry configuration
        """
        self.config = config or RetryConfig()

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for retry attempt.

        Uses exponential backoff with optional jitter.

        Args:
            attempt: Retry attempt number (0-based)

        Returns:
            Delay in seconds
        """
        delay = self.config.base_delay * (self.config.exponential_base ** attempt)
        delay = min(delay, self.config.max_delay)

        if self.config.jitter:
            import random
            delay = delay * (0.5 + random.random())

        return delay

    def should_retry(self, exception: Exception) -> bool:
        """
        Check if exception is retryable.

        Args:
            exception: The exception that occurred

        Returns:
            True if should retry, False otherwise
        """
        # Check non-retryable first
        if isinstance(exception, self.config.non_retryable_exceptions):
            return False

        # Check retryable
        return isinstance(exception, self.config.retryable_exceptions)


def retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
    circuit_breaker: Optional[CircuitBreaker] = None
):
    """
    Retry decorator for async functions.

    Args:
        max_retries: Maximum retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        retryable_exceptions: Exceptions that trigger retry
        circuit_breaker: Optional circuit breaker

    Returns:
        Decorated function
    """
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
        retryable_exceptions=retryable_exceptions
    )
    handler = RetryHandler(config)

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Check circuit breaker
            if circuit_breaker and not circuit_breaker.is_available():
                raise RuntimeError(
                    f"Circuit breaker '{circuit_breaker.name}' is OPEN"
                )

            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    result = await func(*args, **kwargs)

                    # Record success
                    if circuit_breaker:
                        circuit_breaker.record_success()

                    return result

                except Exception as e:
                    last_exception = e

                    # Record failure
                    if circuit_breaker:
                        circuit_breaker.record_failure()

                    # Check if retryable
                    if not handler.should_retry(e):
                        logger.error(
                            f"Non-retryable error in {func.__name__}: {e}"
                        )
                        raise

                    # Check if max retries reached
                    if attempt >= max_retries:
                        logger.error(
                            f"Max retries ({max_retries}) reached for {func.__name__}: {e}"
                        )
                        raise

                    # Calculate delay
                    delay = handler.calculate_delay(attempt)

                    logger.warning(
                        f"Retry {attempt + 1}/{max_retries} for {func.__name__} "
                        f"after {delay:.2f}s: {e}"
                    )

                    await asyncio.sleep(delay)

            # Should not reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


async def with_retry(
    func: Callable,
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    retryable_exceptions: tuple = (Exception,),
    **kwargs
) -> Any:
    """
    Execute function with retry logic.

    Args:
        func: Async function to execute
        *args: Function arguments
        max_retries: Maximum retry attempts
        base_delay: Initial delay in seconds
        retryable_exceptions: Exceptions that trigger retry
        **kwargs: Function keyword arguments

    Returns:
        Function result
    """
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=base_delay,
        retryable_exceptions=retryable_exceptions
    )
    handler = RetryHandler(config)

    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)

        except Exception as e:
            last_exception = e

            if not handler.should_retry(e):
                raise

            if attempt >= max_retries:
                raise

            delay = handler.calculate_delay(attempt)
            logger.warning(
                f"Retry {attempt + 1}/{max_retries}: {e}, "
                f"waiting {delay:.2f}s"
            )
            await asyncio.sleep(delay)

    if last_exception:
        raise last_exception


# Global circuit breakers for common services
_circuit_breakers: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str) -> CircuitBreaker:
    """
    Get or create a circuit breaker by name.

    Args:
        name: Circuit breaker name

    Returns:
        CircuitBreaker instance
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name)
    return _circuit_breakers[name]
