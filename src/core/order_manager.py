"""
Order Manager - High-level order execution with TWAP support.

Handles order execution with automatic TWAP routing for large orders
and comprehensive partial fill handling.
"""

from datetime import datetime
from typing import Dict, Optional

from src.core.exchange import BinanceExchange
from src.core.logger import get_logger
from src.execution.exceptions import OrderExecutionError
from src.execution.lifecycle import Order, OrderStatus
from src.execution.order_status_poller import OrderStatusPoller, OrderFillResult
from src.execution.twap_executor import TWAPExecutor, TWAPResult, PrecisionHandler
from src.strategies.base import Signal

logger = get_logger(__name__)


class OrderManager:
    """
    High-level order execution manager with TWAP support.
    
    Automatically routes large orders through TWAP to minimize slippage,
    and handles partial fills gracefully. This is the main entry point
    for order execution in the trading bot.
    
    Features:
    - Automatic TWAP routing for large orders (> $1000)
    - Direct market order execution for small orders
    - Partial fill handling
    - Order status monitoring
    - Comprehensive error handling
    """
    
    def __init__(
        self,
        exchange: BinanceExchange,
        twap_executor: Optional[TWAPExecutor] = None,
        order_status_poller: Optional[OrderStatusPoller] = None,
        precision_handler: Optional[PrecisionHandler] = None,
        alert_manager: Optional[object] = None,  # Optional alert manager
        db: Optional[object] = None  # Optional database client
    ):
        """
        Initialize order manager.
        
        Args:
            exchange: Exchange client for order execution
            twap_executor: TWAP executor instance (created if None)
            order_status_poller: Order status poller instance (created if None)
            precision_handler: Precision handler for rounding (created if None)
            alert_manager: Optional alert manager for notifications
            db: Optional database client for order persistence
        """
        if exchange is None:
            raise ValueError("Exchange is required")
        
        self.exchange = exchange
        self.alert_manager = alert_manager
        self.db = db
        
        # Initialize components if not provided
        self.precision_handler = precision_handler or PrecisionHandler()
        
        if twap_executor is None:
            twap_config = {
                'default_num_chunks': 5,
                'default_interval_seconds': 30,
                'max_price_deviation_percent': 0.01,
                'min_chunk_value_usdt': 50,
                'check_spread': True,
                'max_spread_percent': 0.005,
                'twap_threshold_usdt': 1000
            }
            self.twap_executor = TWAPExecutor(
                exchange=exchange,
                precision_handler=self.precision_handler,
                config=twap_config
            )
        else:
            self.twap_executor = twap_executor
        
        if order_status_poller is None:
            self.order_status_poller = OrderStatusPoller(
                exchange=exchange,
                poll_interval_seconds=2.0,
                default_timeout_seconds=30
            )
        else:
            self.order_status_poller = order_status_poller
        
        logger.info("OrderManager initialized with TWAP and order status polling support")
    
    async def execute_order_with_twap_support(
        self,
        signal: Signal,
        quantity: float
    ) -> Order:
        """
        Execute order with automatic TWAP for large orders.
        
        Logic:
        1. Check if order should use TWAP (based on order value)
        2. If yes → Execute via TWAP executor
        3. If no → Execute as single market order
        4. Handle partial fills in both cases
        
        Args:
            signal: Trading signal with symbol, side, entry_price
            quantity: Order quantity (base asset)
            
        Returns:
            Primary order (or aggregated TWAP order)
            
        Raises:
            OrderExecutionError: If order execution fails
            ValueError: If signal or quantity is invalid
            
        Example:
            >>> signal = Signal(symbol='BTCUSDT', side='BUY', entry_price=42000, ...)
            >>> order = await order_manager.execute_order_with_twap_support(signal, 0.5)
            >>> print(f"Order filled: {order.filled_quantity} @ {order.avg_fill_price}")
        """
        if signal is None:
            raise ValueError("Signal cannot be None")
        if quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {quantity}")
        if signal.entry_price <= 0:
            raise ValueError(f"Entry price must be positive, got {signal.entry_price}")
        
        symbol = signal.symbol
        side = signal.side
        current_price = signal.entry_price
        
        logger.info(
            f"Executing order: {side} {quantity} {symbol} @ {current_price:.2f} "
            f"(value=${quantity * current_price:.2f})"
        )
        
        # Check if TWAP needed
        if self.twap_executor.should_use_twap(symbol, quantity, current_price):
            logger.info(f"Using TWAP execution for {symbol} (qty={quantity}, value=${quantity * current_price:.2f})")
            
            try:
                # Execute TWAP
                twap_result = await self.twap_executor.execute_twap(
                    symbol=symbol,
                    side=side,
                    total_quantity=quantity,
                    current_price=current_price
                )
                
                # Create aggregated order record
                order_id = f"{symbol}_{side}_twap_{datetime.now().timestamp()}"
                
                # Determine final status
                if twap_result.total_filled >= quantity * 0.99:  # 99% filled = FILLED
                    final_status = OrderStatus.FILLED
                elif twap_result.total_filled > 0:
                    final_status = OrderStatus.PARTIALLY_FILLED
                else:
                    final_status = OrderStatus.REJECTED
                
                order = Order(
                    id=order_id,
                    symbol=symbol,
                    side=side,
                    order_type='twap',
                    quantity=quantity,
                    price=None,  # TWAP uses market orders
                    status=final_status,
                    filled_quantity=twap_result.total_filled,
                    avg_fill_price=twap_result.average_price,
                    exchange_order_id=None,  # TWAP has multiple orders
                    metadata={
                        'execution_type': 'TWAP',
                        'chunks_executed': twap_result.chunks_executed,
                        'total_chunks': twap_result.total_chunks,
                        'stopped_early': twap_result.stopped_early,
                        'stop_reason': twap_result.stop_reason,
                        'slippage_percent': twap_result.slippage_percent,
                        'execution_time_seconds': twap_result.execution_time_seconds,
                        'twap_orders': [o.id for o in twap_result.orders] if twap_result.orders else []
                    }
                )
                
                # Store fees in metadata (Order doesn't have fees field)
                order.metadata['fees'] = twap_result.total_fees
                
                # Save to database if available
                if self.db:
                    try:
                        await self.db.save_order(order)
                    except Exception as e:
                        logger.warning(f"Failed to save order to database: {e}")
                
                logger.info(
                    f"TWAP order complete: {order_id} - "
                    f"filled={twap_result.total_filled}/{quantity} "
                    f"({twap_result.total_filled/quantity*100:.1f}%), "
                    f"avg_price={twap_result.average_price:.2f}, "
                    f"slippage={twap_result.slippage_percent:+.2f}%"
                )
                
                # Handle partial fill if needed
                if final_status == OrderStatus.PARTIALLY_FILLED:
                    fill_result = OrderFillResult(
                        status='PARTIAL',
                        filled_quantity=twap_result.total_filled,
                        avg_fill_price=twap_result.average_price,
                        fees=twap_result.total_fees,
                        fill_time=datetime.now(),
                        polls_count=twap_result.chunks_executed
                    )
                    await self._handle_partial_fill(order, fill_result)
                
                return order
            
            except Exception as e:
                logger.error(f"TWAP execution failed: {e}", exc_info=True)
                raise OrderExecutionError(f"TWAP execution failed: {e}")
        
        else:
            # Single market order
            logger.info(f"Using direct market order for {symbol} (qty={quantity}, value=${quantity * current_price:.2f})")
            
            return await self._execute_market_order(symbol, side, quantity, signal)
    
    async def _execute_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        signal: Optional[Signal] = None
    ) -> Order:
        """
        Execute single market order with fill monitoring.
        
        Args:
            symbol: Trading pair
            side: BUY or SELL
            quantity: Order quantity
            signal: Optional signal for metadata
            
        Returns:
            Filled order
            
        Raises:
            OrderExecutionError: If order execution fails
        """
        try:
            # Round to exchange precision
            quantity = self.precision_handler.round_quantity(symbol, quantity)
            
            if quantity <= 0:
                raise OrderExecutionError(f"Invalid quantity after rounding: {quantity}")
            
            logger.debug(f"Submitting market order: {side} {quantity} {symbol}")
            
            # Submit order
            response = await self.exchange.place_order(
                symbol=symbol,
                side=side,
                order_type='MARKET',
                quantity=quantity
            )
            
            exchange_order_id = response.get('orderId')
            if exchange_order_id is None:
                raise OrderExecutionError("Order placed but no order ID returned")
            
            # Create order record
            order_id = f"{symbol}_{side}_market_{datetime.now().timestamp()}"
            order = Order(
                id=order_id,
                symbol=symbol,
                side=side,
                order_type='market',
                quantity=quantity,
                price=None,  # Market order
                status=OrderStatus.SUBMITTED,
                exchange_order_id=str(exchange_order_id),
                metadata={
                    'execution_type': 'MARKET',
                    'signal_strategy': signal.strategy if signal else None
                }
            )
            
            # Save to database if available
            if self.db:
                try:
                    await self.db.save_order(order)
                except Exception as e:
                    logger.warning(f"Failed to save order to database: {e}")
            
            # Wait for fill
            fill_result = await self.order_status_poller.wait_for_fill(
                order,
                timeout=30
            )
            
            # Update order with fill result
            order.filled_quantity = fill_result.filled_quantity
            order.avg_fill_price = fill_result.avg_fill_price
            
            # Store fees in metadata (Order doesn't have fees field)
            order.metadata['fees'] = fill_result.fees
            
            # Map fill result status to OrderStatus
            if fill_result.status == 'FILLED':
                order.status = OrderStatus.FILLED
                order.filled_at = fill_result.fill_time
            elif fill_result.status == 'PARTIAL':
                order.status = OrderStatus.PARTIALLY_FILLED
                order.filled_at = fill_result.fill_time
            elif fill_result.status == 'FAILED':
                order.status = OrderStatus.REJECTED
                order.metadata['failure_reason'] = fill_result.failure_reason
            elif fill_result.status == 'TIMEOUT':
                order.status = OrderStatus.EXPIRED
                order.metadata['timeout'] = True
            
            # Update in database if available
            if self.db:
                try:
                    await self.db.update_order(order)
                except Exception as e:
                    logger.warning(f"Failed to update order in database: {e}")
            
            # Handle partial fill
            if fill_result.status == 'PARTIAL':
                await self._handle_partial_fill(order, fill_result)
            
            logger.info(
                f"Market order complete: {order_id} - "
                f"status={order.status.value}, "
                f"filled={order.filled_quantity}/{order.quantity}, "
                f"price={order.avg_fill_price:.2f if order.avg_fill_price else 0:.2f}"
            )
            
            return order
        
        except OrderExecutionError:
            raise
        except Exception as e:
            logger.error(f"Market order execution failed: {e}", exc_info=True)
            raise OrderExecutionError(f"Market order execution failed: {e}")
    
    async def _handle_partial_fill(
        self,
        order: Order,
        fill_result: OrderFillResult
    ) -> None:
        """
        Handle partially filled order.
        
        Strategy: Accept partial fill and adjust position size.
        The position will be created with filled_quantity, not requested quantity.
        Risk calculation was already done on requested quantity, so partial is safer.
        
        Options considered:
        1. Cancel remaining quantity (not implemented - would lose filled portion)
        2. Wait for full fill (not implemented - could timeout)
        3. Accept partial and adjust position (current implementation)
        
        Args:
            order: Partially filled order
            fill_result: Fill result with partial fill details
        """
        filled_percent = (fill_result.filled_quantity / order.quantity * 100) if order.quantity > 0 else 0.0
        
        logger.warning(
            f"⚠️ Partial fill detected: {order.symbol} "
            f"filled={fill_result.filled_quantity}/{order.quantity} ({filled_percent:.1f}%) "
            f"@ {fill_result.avg_fill_price:.2f}"
        )
        
        # Strategy: Accept partial fill
        # Position will be created with filled_quantity, not requested quantity
        # Risk calculation already done on requested quantity, so partial is safer
        
        # Send alert if alert manager available
        if self.alert_manager:
            try:
                await self.alert_manager.send_alert(
                    level='WARNING',
                    message=f"Partial fill: {order.symbol} {filled_percent:.1f}% filled",
                    data={
                        'order_id': order.id,
                        'symbol': order.symbol,
                        'side': order.side,
                        'requested': order.quantity,
                        'filled': fill_result.filled_quantity,
                        'filled_percent': filled_percent,
                        'avg_fill_price': fill_result.avg_fill_price,
                        'fees': fill_result.fees
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to send partial fill alert: {e}")
        
        # Log additional details
        logger.info(
            f"Partial fill accepted: Position will be created with "
            f"{fill_result.filled_quantity} {order.symbol} "
            f"(requested: {order.quantity}, difference: {order.quantity - fill_result.filled_quantity})"
        )
