"""
TWAP (Time-Weighted Average Price) Executor.

Splits large orders into smaller chunks executed over time to minimize
market impact and slippage. This is critical for large order execution.
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from src.core.exchange import BinanceExchange
from src.core.logger import get_logger
from src.execution.exceptions import OrderExecutionError
from src.execution.lifecycle import Order, OrderStatus

logger = get_logger(__name__)


class TWAPExecutionError(OrderExecutionError):
    """Exception raised when TWAP execution fails."""
    pass


@dataclass
class TWAPResult:
    """Result of TWAP execution."""
    orders: List[Order]
    total_filled: float
    average_price: float
    total_fees: float
    slippage_percent: float
    execution_time_seconds: float
    stopped_early: bool
    stop_reason: Optional[str]
    chunks_executed: int
    total_chunks: int


class PrecisionHandler:
    """
    Simple precision handler for quantity/price rounding.
    
    For crypto exchanges, typically round to 8 decimal places.
    """
    
    @staticmethod
    def round_quantity(symbol: str, quantity: float) -> float:
        """
        Round quantity to exchange precision.
        
        Args:
            symbol: Trading symbol (not used in simple implementation)
            quantity: Quantity to round
            
        Returns:
            Rounded quantity
        """
        # Simple rounding to 8 decimal places (standard for crypto)
        return round(quantity, 8)


class TWAPExecutor:
    """
    Time-Weighted Average Price order executor.
    
    Splits large orders into smaller chunks executed over time
    to minimize slippage and market impact.
    
    Algorithm:
    1. Split total quantity into N equal chunks
    2. Execute 1 chunk every T seconds
    3. Monitor fill status for each chunk
    4. Stop early if:
       - Market conditions deteriorate (spread widens)
       - Price moves significantly against us
       - Liquidity dries up
    5. Return aggregated results
    """
    
    def __init__(
        self,
        exchange: BinanceExchange,
        precision_handler: Optional[PrecisionHandler] = None,
        config: Optional[Dict] = None
    ):
        """
        Initialize TWAP executor.
        
        Args:
            exchange: Exchange client for order execution
            precision_handler: For quantity/price rounding (default: simple handler)
            config: Configuration dict with:
                - default_num_chunks: Default chunks (default: 5)
                - default_interval_seconds: Time between chunks (default: 30)
                - max_price_deviation_percent: Stop if price moves (default: 0.01 = 1%)
                - min_chunk_value_usdt: Minimum chunk value (default: 50)
                - check_spread: Check spread before each chunk (default: True)
                - max_spread_percent: Max acceptable spread (default: 0.005 = 0.5%)
                - twap_threshold_usdt: Use TWAP for orders > this value (default: 1000)
        """
        if exchange is None:
            raise ValueError("Exchange is required")
        
        self.exchange = exchange
        self.precision_handler = precision_handler or PrecisionHandler()
        
        config = config or {}
        self.default_num_chunks = config.get('default_num_chunks', 5)
        self.default_interval = config.get('default_interval_seconds', 30)
        self.max_price_deviation = config.get('max_price_deviation_percent', 0.01)
        self.min_chunk_value = config.get('min_chunk_value_usdt', 50)
        self.check_spread = config.get('check_spread', True)
        self.max_spread = config.get('max_spread_percent', 0.005)
        self.twap_threshold_usdt = config.get('twap_threshold_usdt', 1000)
        
        logger.info(
            f"TWAPExecutor initialized: "
            f"chunks={self.default_num_chunks}, "
            f"interval={self.default_interval}s, "
            f"threshold=${self.twap_threshold_usdt}"
        )
    
    def should_use_twap(
        self,
        symbol: str,
        quantity: float,
        current_price: float
    ) -> bool:
        """
        Determine if TWAP should be used for this order.
        
        Use TWAP if:
        - Order value > threshold (e.g., $1000)
        
        Args:
            symbol: Trading pair
            quantity: Order quantity
            current_price: Current market price
            
        Returns:
            True if TWAP recommended, False for direct execution
        """
        order_value = quantity * current_price
        
        # Use TWAP for orders > threshold
        if order_value > self.twap_threshold_usdt:
            logger.info(
                f"TWAP recommended for {symbol}: "
                f"order_value=${order_value:.2f} > ${self.twap_threshold_usdt}"
            )
            return True
        
        return False
    
    async def execute_twap(
        self,
        symbol: str,
        side: str,
        total_quantity: float,
        current_price: float,
        num_chunks: Optional[int] = None,
        interval_seconds: Optional[int] = None
    ) -> TWAPResult:
        """
        Execute TWAP order.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            side: 'BUY' or 'SELL'
            total_quantity: Total quantity to execute
            current_price: Starting price (for deviation check)
            num_chunks: Number of chunks (default: config value)
            interval_seconds: Time between chunks (default: config value)
            
        Returns:
            TWAPResult with:
            - orders: List of executed chunk orders
            - total_filled: Total quantity filled
            - average_price: Weighted average fill price
            - total_fees: Sum of all fees
            - slippage_percent: Actual slippage
            - execution_time_seconds: Total time taken
            - stopped_early: Whether execution stopped before all chunks
            - stop_reason: Reason if stopped early
            
        Raises:
            TWAPExecutionError: If execution fails
        """
        if total_quantity <= 0:
            raise TWAPExecutionError(f"Invalid quantity: {total_quantity}")
        if current_price <= 0:
            raise TWAPExecutionError(f"Invalid price: {current_price}")
        
        num_chunks = num_chunks or self.default_num_chunks
        interval_seconds = interval_seconds or self.default_interval
        
        if num_chunks <= 0:
            raise TWAPExecutionError(f"Invalid num_chunks: {num_chunks}")
        if interval_seconds <= 0:
            raise TWAPExecutionError(f"Invalid interval_seconds: {interval_seconds}")
        
        logger.info(
            f"Starting TWAP execution: {side} {total_quantity} {symbol} "
            f"(chunks={num_chunks}, interval={interval_seconds}s, "
            f"total_time={num_chunks * interval_seconds}s)"
        )
        
        # Calculate chunk size
        chunk_size = total_quantity / num_chunks
        
        # Round to exchange precision
        chunk_size = self.precision_handler.round_quantity(symbol, chunk_size)
        
        # Validate minimum chunk value
        chunk_value = chunk_size * current_price
        if chunk_value < self.min_chunk_value:
            logger.warning(
                f"Chunk value ${chunk_value:.2f} < minimum ${self.min_chunk_value:.2f}, "
                f"reducing chunks to maintain minimum"
            )
            # Adjust number of chunks
            num_chunks = int(total_quantity * current_price / self.min_chunk_value)
            num_chunks = max(1, num_chunks)  # At least 1 chunk
            chunk_size = total_quantity / num_chunks
            chunk_size = self.precision_handler.round_quantity(symbol, chunk_size)
            logger.info(f"Adjusted to {num_chunks} chunks (chunk_size={chunk_size})")
        
        # Execution tracking
        start_time = time.time()
        orders: List[Order] = []
        total_filled = 0.0
        total_cost = 0.0  # For average price calculation
        total_fees = 0.0
        stopped_early = False
        stop_reason: Optional[str] = None
        
        # Execute chunks
        for chunk_index in range(num_chunks):
            logger.info(
                f"Executing chunk {chunk_index + 1}/{num_chunks}: "
                f"{side} {chunk_size} {symbol}"
            )
            
            try:
                # Pre-execution checks
                if self.check_spread:
                    spread_ok, spread = await self._check_spread(symbol)
                    if not spread_ok:
                        logger.warning(
                            f"Spread too wide: {spread*100:.2f}% > {self.max_spread*100:.2f}%, "
                            f"stopping TWAP"
                        )
                        stopped_early = True
                        stop_reason = f"SPREAD_TOO_WIDE: {spread*100:.2f}%"
                        break
                
                # Check price deviation
                new_price = await self.exchange.get_ticker_price(symbol)
                if new_price is None:
                    logger.error(f"Could not get price for {symbol}, stopping TWAP")
                    stopped_early = True
                    stop_reason = "PRICE_FETCH_ERROR"
                    break
                
                price_deviation = abs(new_price - current_price) / current_price
                
                if price_deviation > self.max_price_deviation:
                    logger.warning(
                        f"Price deviated {price_deviation*100:.2f}% from start "
                        f"({current_price:.2f} → {new_price:.2f}), stopping TWAP"
                    )
                    stopped_early = True
                    stop_reason = f"PRICE_DEVIATION: {price_deviation*100:.2f}%"
                    break
                
                # Adjust chunk size for last chunk to account for rounding
                if chunk_index == num_chunks - 1:
                    # Last chunk: fill remaining quantity
                    remaining = total_quantity - total_filled
                    chunk_size = self.precision_handler.round_quantity(symbol, remaining)
                    if chunk_size <= 0:
                        logger.info("No remaining quantity for last chunk")
                        break
                
                # Execute chunk
                order = await self._execute_chunk(
                    symbol=symbol,
                    side=side,
                    quantity=chunk_size,
                    chunk_index=chunk_index
                )
                
                orders.append(order)
                
                # Update totals
                if order.status in [OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED]:
                    filled_qty = order.filled_quantity or 0.0
                    fill_price = order.avg_fill_price or new_price
                    
                    total_filled += filled_qty
                    total_cost += fill_price * filled_qty
                    
                    # Estimate fees (0.1% for Binance spot)
                    chunk_fees = fill_price * filled_qty * 0.001
                    total_fees += chunk_fees
                
                logger.info(
                    f"Chunk {chunk_index + 1} completed: "
                    f"filled={order.filled_quantity or 0.0}/{chunk_size}, "
                    f"price={order.avg_fill_price or 0.0:.2f}, "
                    f"progress={total_filled}/{total_quantity} ({total_filled/total_quantity*100:.1f}%)"
                )
                
                # Wait before next chunk (except for last chunk)
                if chunk_index < num_chunks - 1 and not stopped_early:
                    logger.debug(f"Waiting {interval_seconds}s before next chunk")
                    await asyncio.sleep(interval_seconds)
            
            except Exception as e:
                logger.error(
                    f"Error executing chunk {chunk_index + 1}: {e}",
                    exc_info=True
                )
                stopped_early = True
                stop_reason = f"ERROR: {str(e)}"
                break
        
        # Calculate results
        execution_time = time.time() - start_time
        
        if total_filled > 0:
            average_price = total_cost / total_filled
            slippage_percent = ((average_price - current_price) / current_price) * 100
            if side == 'SELL':
                slippage_percent = -slippage_percent  # Invert for sells
        else:
            average_price = 0.0
            slippage_percent = 0.0
        
        result = TWAPResult(
            orders=orders,
            total_filled=total_filled,
            average_price=average_price,
            total_fees=total_fees,
            slippage_percent=slippage_percent,
            execution_time_seconds=execution_time,
            stopped_early=stopped_early,
            stop_reason=stop_reason,
            chunks_executed=len(orders),
            total_chunks=num_chunks
        )
        
        fill_percent = (total_filled / total_quantity * 100) if total_quantity > 0 else 0.0
        
        logger.info(
            f"TWAP execution complete: "
            f"filled={total_filled}/{total_quantity} ({fill_percent:.1f}%), "
            f"avg_price={average_price:.2f}, "
            f"slippage={slippage_percent:+.2f}%, "
            f"time={execution_time:.1f}s, "
            f"stopped_early={stopped_early}"
        )
        
        return result
    
    async def _execute_chunk(
        self,
        symbol: str,
        side: str,
        quantity: float,
        chunk_index: int
    ) -> Order:
        """
        Execute single chunk as market order.
        
        Args:
            symbol: Trading pair
            side: 'BUY' or 'SELL'
            quantity: Chunk quantity
            chunk_index: Index of this chunk (for logging)
            
        Returns:
            Filled order
            
        Raises:
            TWAPExecutionError: If order fails
        """
        try:
            # Create market order
            response = await self.exchange.place_order(
                symbol=symbol,
                side=side,
                order_type='MARKET',
                quantity=quantity
            )
            
            exchange_order_id = response.get('orderId')
            if exchange_order_id is None:
                raise TWAPExecutionError("Order placed but no order ID returned")
            
            # Convert order ID to int if needed
            if isinstance(exchange_order_id, str):
                exchange_order_id_int = int(exchange_order_id)
            else:
                exchange_order_id_int = exchange_order_id
            
            # Create order record
            order_id = f"{symbol}_{side}_twap_chunk_{chunk_index}_{datetime.now().timestamp()}"
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
                    'twap_chunk': chunk_index,
                    'execution_type': 'TWAP'
                }
            )
            
            # Wait for fill
            await self._wait_for_fill(order, exchange_order_id_int, symbol, timeout=30)
            
            return order
        
        except TWAPExecutionError:
            raise
        except Exception as e:
            logger.error(f"Chunk execution failed: {e}", exc_info=True)
            raise TWAPExecutionError(f"Failed to execute chunk {chunk_index}: {e}")
    
    async def _wait_for_fill(
        self,
        order: Order,
        exchange_order_id: int,
        symbol: str,
        timeout: int = 30
    ) -> None:
        """
        Wait for order to fill with polling.
        
        Args:
            order: Order object to monitor
            exchange_order_id: Exchange order ID
            symbol: Trading symbol
            timeout: Timeout in seconds
        """
        timeout_time = datetime.now().timestamp() + timeout
        poll_interval = 2.0
        
        logger.debug(f"Waiting for chunk order {exchange_order_id} to fill (timeout: {timeout}s)")
        
        while datetime.now().timestamp() < timeout_time:
            try:
                # Check order status on exchange
                order_status = await self.exchange.get_order_status(
                    symbol,
                    exchange_order_id
                )
                
                status_str = order_status.get('status', '').upper()
                executed_qty = float(order_status.get('executedQty', 0))
                price = order_status.get('price')
                avg_price = order_status.get('avgPrice')
                
                if status_str == 'FILLED':
                    # Fully filled
                    fill_price = float(price) if price else None
                    if fill_price is None and avg_price:
                        fill_price = float(avg_price)
                    if fill_price is None:
                        fill_price = 0.0
                    
                    order.status = OrderStatus.FILLED
                    order.filled_quantity = executed_qty
                    order.avg_fill_price = fill_price
                    order.filled_at = datetime.now()
                    
                    logger.info(
                        f"Chunk order {exchange_order_id} FILLED: "
                        f"{executed_qty} @ {fill_price:.2f}"
                    )
                    return
                
                elif status_str == 'PARTIALLY_FILLED':
                    # Partially filled - update and continue waiting
                    fill_price = float(price) if price else None
                    if fill_price is None and avg_price:
                        fill_price = float(avg_price)
                    if fill_price is None:
                        fill_price = 0.0
                    
                    order.status = OrderStatus.PARTIALLY_FILLED
                    order.filled_quantity = executed_qty
                    order.avg_fill_price = fill_price
                    
                    logger.debug(
                        f"Chunk order {exchange_order_id} PARTIALLY FILLED: "
                        f"{executed_qty}/{order.quantity}"
                    )
                    # Continue waiting for full fill
                
                elif status_str in ['CANCELED', 'CANCELLED', 'REJECTED', 'EXPIRED']:
                    # Order failed
                    order.status = OrderStatus.REJECTED
                    logger.warning(
                        f"Chunk order {exchange_order_id} {status_str}: "
                        f"filled={executed_qty}/{order.quantity}"
                    )
                    return
                
                # Wait before next check
                await asyncio.sleep(poll_interval)
            
            except Exception as e:
                logger.error(f"Error checking chunk order status: {e}")
                await asyncio.sleep(poll_interval)
        
        # Timeout - get final status
        logger.warning(
            f"Chunk order {exchange_order_id} timed out after {timeout}s"
        )
        try:
            order_status = await self.exchange.get_order_status(
                symbol,
                exchange_order_id
            )
            executed_qty = float(order_status.get('executedQty', 0))
            order.filled_quantity = executed_qty
            order.status = OrderStatus.PARTIALLY_FILLED if executed_qty > 0 else OrderStatus.EXPIRED
        except Exception:
            order.status = OrderStatus.EXPIRED
    
    async def _check_spread(self, symbol: str) -> Tuple[bool, float]:
        """
        Check if current spread is acceptable.
        
        Args:
            symbol: Trading pair
            
        Returns:
            (spread_ok, spread_percent)
        """
        try:
            # Get order book
            ob = await self.exchange.get_order_book(symbol, limit=5)
            
            if not ob or 'bids' not in ob or 'asks' not in ob:
                logger.warning(f"Invalid order book data for {symbol}, assuming OK")
                return True, 0.0
            
            bids = ob['bids']
            asks = ob['asks']
            
            if not bids or not asks:
                logger.warning(f"Empty order book for {symbol}, assuming OK")
                return True, 0.0
            
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
            
            spread_percent = (best_ask - best_bid) / best_bid
            
            spread_ok = spread_percent <= self.max_spread
            
            if not spread_ok:
                logger.debug(
                    f"Spread check for {symbol}: {spread_percent*100:.3f}% "
                    f"(threshold: {self.max_spread*100:.3f}%)"
                )
            
            return spread_ok, spread_percent
        
        except Exception as e:
            logger.error(f"Error checking spread for {symbol}: {e}")
            # Default to OK on error (don't block execution)
            return True, 0.0
