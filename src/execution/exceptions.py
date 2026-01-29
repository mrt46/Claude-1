"""
Order execution exceptions.
"""


class OrderExecutionError(Exception):
    """Exception raised when order execution fails."""
    pass


class OrderStatusError(OrderExecutionError):
    """Exception raised when order status polling fails."""
    pass
