"""
Order Status Poller - Monitor order fill status.

Polls exchange API to monitor order status until it reaches a terminal state
(FILLED, CANCELED, REJECTED) or timeout. Essential for reliable order execution.
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from src.core.exchange import BinanceExchange
from src.core.logger import get_logger
from src.execution.exceptions import OrderExecutionError, OrderStatusError
from src.execution.lifecycle import Order

logger = get_logger(__name__)


@dataclass
class OrderFillResult:
    """
    Result of order fill monitoring.
    
    Contains all details about order execution including fill status,
    quantity filled, average price, fees, and timing information.
    """
    status: str  # 'FILLED', 'PARTIAL', 'FAILED', 'TIMEOUT'
    filled_quantity: float
    avg_fill_price: float
    fees: float
    fill_time: datetime
    polls_count: int
    failure_reason: Optional[str] = None


class OrderStatusPoller:
    """
    Poll exchange for order status updates.
    
    Monitors orders until they reach terminal state (FILLED, CANCELED, REJECTED).
    This is critical because we can't assume instant fills, especially for limit orders.
    
    Features:
    - Polls every N seconds (default: 2s)
    - Handles partial fills
    - Calculates fees from fills array
    - Detects rejections/cancellations
    - Timeout handling
    - Comprehensive error handling
    """
    
    def __init__(
        self,
        exchange: BinanceExchange,
        poll_interval_seconds: float = 2.0,
        default_timeout_seconds: int = 30
    ):
        """
        Initialize order status poller.
        
        Args:
            exchange: Exchange client for API calls
            poll_interval_seconds: Time between status checks (default: 2.0s).
                Lower values = faster detection but more API calls.
            default_timeout_seconds: Default timeout for polling (default: 30s).
                Orders that don't fill within this time will timeout.
                
        Raises:
            ValueError: If exchange is None or intervals are invalid
        """
        if exchange is None:
            raise ValueError("Exchange is required")
        if poll_interval_seconds <= 0:
            raise ValueError(f"poll_interval_seconds must be positive, got {poll_interval_seconds}")
        if default_timeout_seconds <= 0:
            raise ValueError(f"default_timeout_seconds must be positive, got {default_timeout_seconds}")
        
        self.exchange = exchange
        self.poll_interval = poll_interval_seconds
        self.default_timeout = default_timeout_seconds
        
        logger.info(
            f"OrderStatusPoller initialized: "
            f"interval={poll_interval_seconds}s, "
            f"timeout={default_timeout_seconds}s"
        )
    
    async def wait_for_fill(
        self,
        order: Order,
        timeout: Optional[int] = None
    ) -> OrderFillResult:
        """
        Wait for order to fill (or fail).
        
        Polls order status until:
        - Order is FILLED (fully executed)
        - Order is PARTIALLY_FILLED (returns partial result)
        - Order is CANCELED/REJECTED/EXPIRED (returns failed result)
        - Timeout reached (returns timeout result)
        
        Args:
            order: Order to monitor (must have exchange_order_id and symbol)
            timeout: Max wait time in seconds (default: config value)
            
        Returns:
            OrderFillResult with:
            - status: Final status ('FILLED', 'PARTIAL', 'FAILED', 'TIMEOUT')
            - filled_quantity: Quantity filled
            - avg_fill_price: Average fill price
            - fees: Trading fees paid (in USDT)
            - fill_time: Time when filled (or current time for failures)
            - polls_count: Number of status checks made
            - failure_reason: Reason if failed (for FAILED status)
            
        Raises:
            OrderStatusError: If unable to check status after retries
            ValueError: If order is invalid
            
        Example:
            >>> order = Order(...)
            >>> result = await poller.wait_for_fill(order, timeout=30)
            >>> if result.status == 'FILLED':
            ...     print(f"Filled: {result.filled_quantity} @ {result.avg_fill_price}")
        """
        if order is None:
            raise ValueError("Order cannot be None")
        if not order.exchange_order_id:
            raise ValueError("Order must have exchange_order_id")
        if not order.symbol:
            raise ValueError("Order must have symbol")
        
        timeout = timeout or self.default_timeout
        start_time = time.time()
        polls_count = 0
        max_retries = 3
        consecutive_errors = 0
        
        exchange_order_id = order.exchange_order_id
        # Convert to int if string
        if isinstance(exchange_order_id, str):
            try:
                exchange_order_id_int = int(exchange_order_id)
            except ValueError:
                raise ValueError(f"Invalid exchange_order_id format: {exchange_order_id}")
        else:
            exchange_order_id_int = exchange_order_id
        
        logger.info(
            f"Waiting for order {exchange_order_id_int} ({order.symbol}) to fill "
            f"(timeout={timeout}s, quantity={order.quantity})"
        )
        
        while time.time() - start_time < timeout:
            polls_count += 1
            
            try:
                # Get order status from exchange
                status_data = await self.exchange.get_order_status(
                    symbol=order.symbol,
                    order_id=exchange_order_id_int
                )
                
                consecutive_errors = 0  # Reset error counter on success
                
                status = status_data.get('status', '').upper()
                filled_qty = float(status_data.get('executedQty', 0))
                
                logger.debug(
                    f"Order {exchange_order_id_int} status: {status}, "
                    f"filled: {filled_qty}/{order.quantity} "
                    f"(poll #{polls_count})"
                )
                
                # Check terminal states
                if status == 'FILLED':
                    # Fully filled
                    avg_price = self._extract_avg_price(status_data)
                    fees = self._calculate_fees(status_data)
                    fill_time = self._extract_fill_time(status_data)
                    
                    result = OrderFillResult(
                        status='FILLED',
                        filled_quantity=filled_qty,
                        avg_fill_price=avg_price,
                        fees=fees,
                        fill_time=fill_time,
                        polls_count=polls_count
                    )
                    
                    logger.info(
                        f"✅ Order {exchange_order_id_int} FILLED: "
                        f"{filled_qty}/{order.quantity} @ {avg_price:.2f}, "
                        f"fees=${fees:.4f}, polls={polls_count}"
                    )
                    
                    return result
                
                elif status == 'PARTIALLY_FILLED':
                    # Partially filled - return partial result
                    avg_price = self._extract_avg_price(status_data)
                    fees = self._calculate_fees(status_data)
                    fill_time = self._extract_fill_time(status_data)
                    
                    fill_percent = (filled_qty / order.quantity * 100) if order.quantity > 0 else 0.0
                    
                    logger.warning(
                        f"⚠️ Order {exchange_order_id_int} PARTIALLY FILLED: "
                        f"{filled_qty}/{order.quantity} ({fill_percent:.1f}%) @ {avg_price:.2f}"
                    )
                    
                    result = OrderFillResult(
                        status='PARTIAL',
                        filled_quantity=filled_qty,
                        avg_fill_price=avg_price,
                        fees=fees,
                        fill_time=fill_time,
                        polls_count=polls_count
                    )
                    
                    return result
                
                elif status in ['CANCELED', 'CANCELLED', 'REJECTED', 'EXPIRED']:
                    # Order failed
                    logger.error(
                        f"❌ Order {exchange_order_id_int} {status}: "
                        f"filled={filled_qty}/{order.quantity}"
                    )
                    
                    result = OrderFillResult(
                        status='FAILED',
                        filled_quantity=filled_qty,
                        avg_fill_price=0.0,
                        fees=0.0,
                        fill_time=datetime.now(),
                        polls_count=polls_count,
                        failure_reason=status
                    )
                    
                    return result
                
                # Still pending (NEW, PENDING) - wait and poll again
                await asyncio.sleep(self.poll_interval)
            
            except Exception as e:
                consecutive_errors += 1
                logger.error(
                    f"Error polling order {exchange_order_id_int} status (attempt {polls_count}): {e}"
                )
                
                # If too many consecutive errors, raise
                if consecutive_errors >= max_retries:
                    raise OrderStatusError(
                        f"Failed to check order status after {max_retries} consecutive errors: {e}"
                    )
                
                # Wait and retry
                await asyncio.sleep(self.poll_interval)
        
        # Timeout reached
        logger.error(
            f"⏱️ TIMEOUT waiting for order {exchange_order_id_int} "
            f"(waited {timeout}s, polls={polls_count})"
        )
        
        # Get final status to see what was filled
        try:
            status_data = await self.exchange.get_order_status(
                symbol=order.symbol,
                order_id=exchange_order_id_int
            )
            filled_qty = float(status_data.get('executedQty', 0))
            status = status_data.get('status', '').upper()
            
            # If actually filled but we timed out, return FILLED
            if status == 'FILLED':
                avg_price = self._extract_avg_price(status_data)
                fees = self._calculate_fees(status_data)
                fill_time = self._extract_fill_time(status_data)
                
                logger.warning(
                    f"Order {exchange_order_id_int} was FILLED but timeout reached "
                    f"(likely network delay)"
                )
                
                return OrderFillResult(
                    status='FILLED',
                    filled_quantity=filled_qty,
                    avg_fill_price=avg_price,
                    fees=fees,
                    fill_time=fill_time,
                    polls_count=polls_count
                )
        except Exception as e:
            logger.error(f"Error getting final order status: {e}")
            filled_qty = 0.0
        
        # Return timeout result
        result = OrderFillResult(
            status='TIMEOUT',
            filled_quantity=filled_qty,
            avg_fill_price=0.0,
            fees=0.0,
            fill_time=datetime.now(),
            polls_count=polls_count,
            failure_reason='TIMEOUT'
        )
        
        return result
    
    def _extract_avg_price(self, status_data: Dict) -> float:
        """
        Extract average fill price from order status response.
        
        Args:
            status_data: Order status response from exchange
            
        Returns:
            Average fill price, or 0.0 if not available
        """
        # Try avgPrice first (Binance provides this for filled orders)
        if 'avgPrice' in status_data and status_data['avgPrice']:
            try:
                return float(status_data['avgPrice'])
            except (ValueError, TypeError):
                pass
        
        # Try price field
        if 'price' in status_data and status_data['price']:
            try:
                return float(status_data['price'])
            except (ValueError, TypeError):
                pass
        
        # Calculate from fills array if available
        fills = status_data.get('fills', [])
        if fills:
            total_value = 0.0
            total_qty = 0.0
            
            for fill in fills:
                try:
                    fill_price = float(fill.get('price', 0))
                    fill_qty = float(fill.get('qty', 0))
                    total_value += fill_price * fill_qty
                    total_qty += fill_qty
                except (ValueError, TypeError):
                    continue
            
            if total_qty > 0:
                return total_value / total_qty
        
        # Default to 0.0 if nothing available
        logger.warning("Could not extract average price from order status")
        return 0.0
    
    def _extract_fill_time(self, status_data: Dict) -> datetime:
        """
        Extract fill time from order status response.
        
        Args:
            status_data: Order status response from exchange
            
        Returns:
            Fill time as datetime, or current time if not available
        """
        # Try updateTime (when order was last updated)
        if 'updateTime' in status_data:
            try:
                update_time_ms = int(status_data['updateTime'])
                return datetime.fromtimestamp(update_time_ms / 1000)
            except (ValueError, TypeError, OSError):
                pass
        
        # Try time (order creation time)
        if 'time' in status_data:
            try:
                time_ms = int(status_data['time'])
                return datetime.fromtimestamp(time_ms / 1000)
            except (ValueError, TypeError, OSError):
                pass
        
        # Default to current time
        return datetime.now()
    
    def _calculate_fees(self, status_data: Dict) -> float:
        """
        Calculate trading fees from order status response.
        
        Binance provides commission in the 'fills' array. Each fill has:
        - commission: Fee amount
        - commissionAsset: Asset fee is paid in (USDT, BNB, etc.)
        
        Args:
            status_data: Order status response from exchange
            
        Returns:
            Total fees in USDT
        """
        fills = status_data.get('fills', [])
        
        if not fills:
            # No fills array - estimate from executed quantity
            # Binance spot trading fee: 0.1% (0.001)
            executed_qty = float(status_data.get('executedQty', 0))
            avg_price = self._extract_avg_price(status_data)
            
            if avg_price > 0 and executed_qty > 0:
                fill_value = avg_price * executed_qty
                estimated_fee = fill_value * 0.001  # 0.1%
                logger.debug(f"Estimated fees (no fills array): ${estimated_fee:.4f}")
                return estimated_fee
            
            return 0.0
        
        total_fees_usdt = 0.0
        
        for fill in fills:
            try:
                commission = float(fill.get('commission', 0))
                commission_asset = fill.get('commissionAsset', '').upper()
                
                # If commission in USDT, add directly
                if commission_asset == 'USDT':
                    total_fees_usdt += commission
                
                # If commission in other asset (e.g., BNB), convert to USDT
                elif commission_asset and commission > 0:
                    # Get price of commission asset in USDT
                    symbol = f"{commission_asset}USDT"
                    
                    # For now, estimate: if BNB, use approximate conversion
                    # In production, would fetch actual price
                    if commission_asset == 'BNB':
                        # Approximate: assume BNB price ~$300 (will be inaccurate)
                        # Better: fetch actual price from exchange
                        bnb_price_usdt = 300.0  # Placeholder
                        total_fees_usdt += commission * bnb_price_usdt
                        logger.debug(
                            f"Converted {commission} {commission_asset} to USDT "
                            f"(approx ${commission * bnb_price_usdt:.4f})"
                        )
                    else:
                        # Unknown asset - estimate as 0.1% of fill value
                        fill_price = float(fill.get('price', 0))
                        fill_qty = float(fill.get('qty', 0))
                        fill_value = fill_price * fill_qty
                        estimated_fee = fill_value * 0.001
                        total_fees_usdt += estimated_fee
                        logger.debug(
                            f"Estimated fee for {commission_asset}: ${estimated_fee:.4f}"
                        )
                
            except (ValueError, TypeError, KeyError) as e:
                logger.warning(f"Error parsing fill commission: {e}")
                # Estimate fee for this fill
                try:
                    fill_price = float(fill.get('price', 0))
                    fill_qty = float(fill.get('qty', 0))
                    fill_value = fill_price * fill_qty
                    estimated_fee = fill_value * 0.001
                    total_fees_usdt += estimated_fee
                except (ValueError, TypeError):
                    continue
        
        return total_fees_usdt
