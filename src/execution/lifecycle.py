"""
Order lifecycle management.

Tracks order status and handles timeouts/retries.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Optional

from src.core.exchange import BinanceExchange
from src.core.logger import get_logger
from src.execution.exceptions import OrderExecutionError
from src.risk.manager import RiskManager

logger = get_logger(__name__)


class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


@dataclass
class Order:
    """Order data structure."""
    id: str
    symbol: str
    side: str  # 'BUY' or 'SELL'
    order_type: str  # 'market', 'limit', 'twap'
    quantity: float
    price: Optional[float]  # None for market orders
    status: OrderStatus
    filled_quantity: float = 0.0
    avg_fill_price: Optional[float] = None
    created_at: datetime = None
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    exchange_order_id: Optional[str] = None
    metadata: Dict = None
    
    def __post_init__(self):
        """Initialize timestamps."""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.metadata is None:
            self.metadata = {}


class OrderLifecycleManager:
    """
    Manages order lifecycle and monitoring.
    
    Features:
    - Status tracking
    - Timeout handling
    - Retry logic
    - Fill monitoring
    - Position closure
    """
    
    def __init__(
        self,
        exchange: Optional[BinanceExchange] = None,
        risk_manager: Optional[RiskManager] = None,
        market_order_timeout: int = 30,
        limit_order_timeout: int = 300,
        poll_interval: int = 2,
        max_retries: int = 3
    ):
        """
        Initialize lifecycle manager.
        
        Args:
            exchange: Exchange instance for order execution (required for close_position)
            risk_manager: RiskManager instance for position updates (required for close_position)
            market_order_timeout: Timeout for market orders (seconds)
            limit_order_timeout: Timeout for limit orders (seconds)
            poll_interval: Polling interval for status checks (seconds)
            max_retries: Maximum retry attempts
        """
        self.exchange = exchange
        self.risk_manager = risk_manager
        
        self.market_order_timeout = market_order_timeout
        self.limit_order_timeout = limit_order_timeout
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        
        self.orders: Dict[str, Order] = {}
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
    
    def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        order_id: Optional[str] = None
    ) -> Order:
        """
        Create new order.
        
        Args:
            symbol: Trading symbol
            side: 'BUY' or 'SELL'
            order_type: 'market', 'limit', 'twap'
            quantity: Order quantity
            price: Limit price (required for limit orders)
            order_id: Optional order ID
        
        Returns:
            Order object
        """
        if order_id is None:
            order_id = f"{symbol}_{side}_{datetime.now().timestamp()}"
        
        order = Order(
            id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=OrderStatus.PENDING
        )
        
        self.orders[order_id] = order
        logger.info(f"Order created: {order_id} - {symbol} {side} {quantity} @ {price}")
        
        return order
    
    def update_order_status(
        self,
        order_id: str,
        status: OrderStatus,
        filled_quantity: Optional[float] = None,
        avg_fill_price: Optional[float] = None,
        exchange_order_id: Optional[str] = None
    ) -> None:
        """
        Update order status.
        
        Args:
            order_id: Order ID
            status: New status
            filled_quantity: Filled quantity (if filled)
            avg_fill_price: Average fill price (if filled)
            exchange_order_id: Exchange order ID
        """
        if order_id not in self.orders:
            logger.warning(f"Order not found: {order_id}")
            return
        
        order = self.orders[order_id]
        order.status = status
        
        if status == OrderStatus.SUBMITTED:
            order.submitted_at = datetime.now()
            if exchange_order_id:
                order.exchange_order_id = exchange_order_id
        
        if status in [OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED]:
            if filled_quantity is not None:
                order.filled_quantity = filled_quantity
            if avg_fill_price is not None:
                order.avg_fill_price = avg_fill_price
            if status == OrderStatus.FILLED:
                order.filled_at = datetime.now()
        
        logger.info(
            f"Order {order_id} status updated: {status.value} "
            f"(filled: {order.filled_quantity}/{order.quantity})"
        )
    
    async def monitor_order(
        self,
        order_id: str,
        check_status_callback
    ) -> None:
        """
        Monitor order until filled or timeout.
        
        Args:
            order_id: Order ID
            check_status_callback: Async function(order_id) -> OrderStatus
        """
        if order_id not in self.orders:
            logger.warning(f"Order not found for monitoring: {order_id}")
            return
        
        order = self.orders[order_id]
        
        # Determine timeout
        timeout = self.market_order_timeout if order.order_type == 'market' else self.limit_order_timeout
        timeout_time = datetime.now() + timedelta(seconds=timeout)
        
        logger.info(f"Monitoring order {order_id} (timeout: {timeout}s)")
        
        while datetime.now() < timeout_time:
            try:
                # Check status
                status = await check_status_callback(order_id)
                
                if status in [OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELLED]:
                    self.update_order_status(order_id, status)
                    break
                
                await asyncio.sleep(self.poll_interval)
            
            except Exception as e:
                logger.error(f"Error monitoring order {order_id}: {e}")
                await asyncio.sleep(self.poll_interval)
        
        # Check if timed out
        if order.status not in [OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELLED]:
            if datetime.now() >= timeout_time:
                logger.warning(f"Order {order_id} timed out")
                self.update_order_status(order_id, OrderStatus.EXPIRED)
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID."""
        return self.orders.get(order_id)
    
    def get_open_orders(self) -> list:
        """Get all open orders."""
        return [
            order for order in self.orders.values()
            if order.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED]
        ]
    
    async def close_position(
        self,
        position: Dict,
        reason: str,
        emergency: bool = False,
        current_price: Optional[float] = None
    ) -> Order:
        """
        Close position with market order.
        
        Steps:
        1. Get current price (if not provided)
        2. Create opposite side market order
        3. Execute order on exchange
        4. Wait for fill (with timeout)
        5. Calculate PnL (including fees)
        6. Update position in RiskManager
        7. Create order record
        8. Return exit order with PnL
        
        Args:
            position: Position dictionary to close
            reason: Closure reason (STOP_LOSS_HIT, TAKE_PROFIT_HIT, MANUAL, etc)
            emergency: If True, skip some validations and use shorter timeout
            current_price: Optional current price (to avoid extra API call)
            
        Returns:
            Exit Order object with PnL in metadata
            
        Raises:
            OrderExecutionError: If order execution fails
            RuntimeError: If exchange or risk_manager not initialized
        """
        if self.exchange is None:
            raise RuntimeError("Exchange not initialized - required for close_position")
        if self.risk_manager is None:
            raise RuntimeError("RiskManager not initialized - required for close_position")
        
        position_id = position.get('id', 'unknown')
        symbol = position.get('symbol', 'UNKNOWN')
        side = position.get('side', 'BUY')
        quantity = position.get('quantity', 0.0)
        entry_price = position.get('entry_price', 0.0)
        
        if symbol == 'UNKNOWN' or quantity <= 0:
            raise OrderExecutionError(f"Invalid position: {position_id}")
        
        logger.info(
            f"Closing position {position_id} ({symbol} {side}): {reason} "
            f"(emergency={emergency})"
        )
        
        try:
            # Get current price if not provided
            if current_price is None:
                current_price = await self.exchange.get_ticker_price(f"{symbol}")
                if current_price is None:
                    raise OrderExecutionError(f"Could not get price for {symbol}")
            
            # Determine exit side (opposite of entry)
            exit_side = 'SELL' if side == 'BUY' else 'BUY'
            
            # Round quantity (simple rounding to 8 decimal places for crypto)
            quantity = round(quantity, 8)
            
            # Create market order
            logger.debug(
                f"Creating market order: {exit_side} {quantity} {symbol} @ market"
            )
            
            # Execute market order
            order_response = await self.exchange.place_order(
                symbol=symbol,
                side=exit_side,
                order_type='MARKET',
                quantity=quantity
            )
            
            exchange_order_id = order_response.get('orderId')
            if exchange_order_id is None:
                raise OrderExecutionError("Order placed but no order ID returned")
            
            # Convert order ID to int if needed
            if isinstance(exchange_order_id, str):
                exchange_order_id_int = int(exchange_order_id)
            else:
                exchange_order_id_int = exchange_order_id
            
            # Create order record
            order_id = f"{symbol}_{exit_side}_close_{datetime.now().timestamp()}"
            exit_order = Order(
                id=order_id,
                symbol=symbol,
                side=exit_side,
                order_type='market',
                quantity=quantity,
                price=None,  # Market order
                status=OrderStatus.SUBMITTED,
                exchange_order_id=str(exchange_order_id),
                metadata={
                    'closure_reason': reason,
                    'emergency': emergency,
                    'position_id': position_id
                }
            )
            
            self.orders[order_id] = exit_order
            
            # Wait for fill
            timeout = 10 if emergency else self.market_order_timeout
            filled = await self._wait_for_fill(
                exit_order,
                exchange_order_id_int,
                symbol,
                timeout=timeout
            )
            
            if not filled:
                exit_order.status = OrderStatus.EXPIRED
                raise OrderExecutionError(
                    f"Order {order_id} timed out after {timeout}s"
                )
            
            # Check if order was rejected
            if exit_order.status == OrderStatus.REJECTED:
                raise OrderExecutionError(
                    f"Order {order_id} was rejected by exchange"
                )
            
            # Get fill details
            exit_price = exit_order.avg_fill_price
            filled_quantity = exit_order.filled_quantity
            
            if exit_price is None or filled_quantity is None:
                raise OrderExecutionError(
                    f"Order {order_id} filled but missing price/quantity"
                )
            
            # Handle partial fills
            if filled_quantity < quantity:
                logger.warning(
                    f"⚠️ Partial fill: {filled_quantity}/{quantity} for {symbol}"
                )
                # Update position quantity for partial fill
                remaining_quantity = quantity - filled_quantity
                position['quantity'] = remaining_quantity
                # Note: Position remains open with reduced quantity
                # This is a simplified handling - in production, might want to
                # create separate position for remaining quantity
            
            # Calculate PnL
            if side == 'BUY':
                # Long position
                gross_pnl = (exit_price - entry_price) * filled_quantity
            else:
                # Short position
                gross_pnl = (entry_price - exit_price) * filled_quantity
            
            # Subtract fees (0.1% maker/taker for Binance spot)
            entry_fee = entry_price * quantity * 0.001
            exit_fee = exit_price * filled_quantity * 0.001
            net_pnl = gross_pnl - entry_fee - exit_fee
            
            position_value = entry_price * quantity
            pnl_percent = (net_pnl / position_value) * 100 if position_value > 0 else 0.0
            
            # Update position in RiskManager (remove if fully closed)
            if filled_quantity >= quantity:
                self.risk_manager.remove_position(position_id)
                logger.info(f"Position {position_id} fully closed and removed")
            else:
                # Partial fill - update position quantity
                logger.info(
                    f"Position {position_id} partially closed: "
                    f"{filled_quantity}/{quantity}, remaining: {remaining_quantity}"
                )
            
            # Store PnL in order metadata
            exit_order.metadata['pnl'] = net_pnl
            exit_order.metadata['pnl_percent'] = pnl_percent
            exit_order.metadata['entry_price'] = entry_price
            exit_order.metadata['exit_price'] = exit_price
            exit_order.metadata['filled_quantity'] = filled_quantity
            
            # Calculate hold duration if available
            opened_at = position.get('opened_at')
            if opened_at:
                if isinstance(opened_at, str):
                    try:
                        opened_at = datetime.fromisoformat(opened_at.replace('Z', '+00:00'))
                    except Exception:
                        opened_at = None
                
                if opened_at and isinstance(opened_at, datetime):
                    hold_duration = (datetime.now() - opened_at.replace(tzinfo=None)).total_seconds()
                    exit_order.metadata['hold_duration_seconds'] = int(hold_duration)
            
            # Log result
            logger.info(
                f"✅ Position {position_id} closed: "
                f"entry={entry_price:.2f}, exit={exit_price:.2f}, "
                f"PnL=${net_pnl:.2f} ({pnl_percent:+.2f}%), "
                f"filled={filled_quantity}/{quantity}, reason={reason}"
            )
            
            return exit_order
        
        except OrderExecutionError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to close position {position_id}: {e}",
                exc_info=True
            )
            raise OrderExecutionError(f"Position closure failed: {e}")
    
    async def _wait_for_fill(
        self,
        order: Order,
        exchange_order_id: int,
        symbol: str,
        timeout: int = 30
    ) -> bool:
        """
        Wait for order to fill with polling.
        
        Args:
            order: Order object to monitor
            exchange_order_id: Exchange order ID
            symbol: Trading symbol
            timeout: Timeout in seconds
            
        Returns:
            True if filled, False if timeout or rejected
        """
        if self.exchange is None:
            raise RuntimeError("Exchange not initialized")
        
        timeout_time = datetime.now() + timedelta(seconds=timeout)
        
        logger.debug(f"Waiting for order {order.id} to fill (timeout: {timeout}s)")
        
        while datetime.now() < timeout_time:
            try:
                # Check order status on exchange
                order_status = await self.exchange.get_order_status(
                    symbol,
                    exchange_order_id
                )
                
                status_str = order_status.get('status', '').upper()
                executed_qty = float(order_status.get('executedQty', 0))
                price = order_status.get('price')
                
                if status_str == 'FILLED':
                    # Fully filled
                    fill_price = float(price) if price else None
                    if fill_price is None:
                        # Try to get average price from fills
                        fill_price = float(order_status.get('avgPrice', 0))
                    
                    self.update_order_status(
                        order.id,
                        OrderStatus.FILLED,
                        filled_quantity=executed_qty,
                        avg_fill_price=fill_price,
                        exchange_order_id=str(exchange_order_id)
                    )
                    logger.info(f"Order {order.id} filled: {executed_qty} @ {fill_price}")
                    return True
                
                elif status_str == 'PARTIALLY_FILLED':
                    # Partially filled
                    fill_price = float(price) if price else None
                    if fill_price is None:
                        fill_price = float(order_status.get('avgPrice', 0))
                    
                    self.update_order_status(
                        order.id,
                        OrderStatus.PARTIALLY_FILLED,
                        filled_quantity=executed_qty,
                        avg_fill_price=fill_price,
                        exchange_order_id=str(exchange_order_id)
                    )
                    logger.info(f"Order {order.id} partially filled: {executed_qty}/{order.quantity}")
                    # Continue waiting for full fill
                
                elif status_str == 'CANCELED' or status_str == 'CANCELLED':
                    # Order cancelled
                    self.update_order_status(
                        order.id,
                        OrderStatus.CANCELLED,
                        exchange_order_id=str(exchange_order_id)
                    )
                    logger.warning(f"Order {order.id} was cancelled")
                    return False
                
                elif status_str == 'REJECTED' or status_str == 'EXPIRED':
                    # Order rejected or expired
                    self.update_order_status(
                        order.id,
                        OrderStatus.REJECTED,
                        exchange_order_id=str(exchange_order_id)
                    )
                    logger.warning(f"Order {order.id} was rejected/expired")
                    return False
                
                # Wait before next check
                await asyncio.sleep(self.poll_interval)
            
            except Exception as e:
                logger.error(f"Error checking order status: {e}")
                await asyncio.sleep(self.poll_interval)
        
        # Timeout
        logger.warning(f"Order {order.id} timed out after {timeout}s")
        self.update_order_status(order.id, OrderStatus.EXPIRED)
        return False