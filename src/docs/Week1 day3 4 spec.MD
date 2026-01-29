# 📋 WEEK 1 - DAY 3-4 DETAILED SPECIFICATION
## Order Execution Safety (TWAP, Partial Fills, Signal Deduplication)

**Duration:** 2 days  
**Priority:** CRITICAL ❌  
**Dependencies:** Day 1-2 (Position Monitoring must be done first)

---

## 🎯 OBJECTIVES

1. **TWAP Executor:** Split large orders to minimize slippage
2. **Partial Fill Handler:** Track and handle partial order fills correctly
3. **Signal Deduplicator:** Prevent duplicate positions from same signal
4. **Order Status Polling:** Monitor order fill status reliably

**Why Critical:** Without these, bot will:
- Suffer excessive slippage on large orders
- Open duplicate positions (2x risk)
- Have incorrect position sizes
- Miss order fills

---

## 📂 FILES TO CREATE/MODIFY

```
src/execution/
├── twap_executor.py              (NEW - 350 lines)
├── signal_deduplicator.py        (NEW - 150 lines)
└── order_status_poller.py        (NEW - 200 lines)

src/core/
└── order_manager.py              (MODIFY - add partial fill handling)

src/models/
└── signal.py                     (MODIFY - add signal ID generation)

tests/unit/
├── test_twap_executor.py         (NEW - 200 lines)
├── test_signal_deduplicator.py   (NEW - 100 lines)
└── test_order_status_poller.py   (NEW - 150 lines)

tests/integration/
└── test_order_execution.py       (NEW - 250 lines)
```

---

## 📝 DETAILED SPECIFICATIONS

---

## 1. TWAP EXECUTOR

### File: `src/execution/twap_executor.py`

#### Class: `TWAPExecutor`

**Purpose:** Execute large orders by splitting into smaller chunks over time to minimize market impact and slippage.

**Algorithm:**
```
TWAP (Time-Weighted Average Price):
1. Split total quantity into N equal chunks
2. Execute 1 chunk every T seconds
3. Monitor fill status for each chunk
4. Stop early if:
   - Market conditions deteriorate (spread widens)
   - Price moves significantly against us
   - Liquidity dries up
5. Return aggregated results
```

**Constructor:**
```python
class TWAPExecutor:
    """
    Time-Weighted Average Price order executor.
    
    Splits large orders into smaller chunks executed over time
    to minimize slippage and market impact.
    """
    
    def __init__(
        self,
        exchange: BinanceExchange,
        precision_handler: PrecisionHandler,
        config: dict
    ):
        """
        Initialize TWAP executor.
        
        Args:
            exchange: Exchange client for order execution
            precision_handler: For quantity/price rounding
            config: Configuration dict with:
                - default_num_chunks: Default chunks (default: 5)
                - default_interval_seconds: Time between chunks (default: 30)
                - max_price_deviation_percent: Stop if price moves (default: 0.01)
                - min_chunk_value_usdt: Minimum chunk value (default: 50)
                - check_spread: Check spread before each chunk (default: True)
                - max_spread_percent: Max acceptable spread (default: 0.005)
        """
        self.exchange = exchange
        self.precision_handler = precision_handler
        
        self.default_num_chunks = config.get('default_num_chunks', 5)
        self.default_interval = config.get('default_interval_seconds', 30)
        self.max_price_deviation = config.get('max_price_deviation_percent', 0.01)
        self.min_chunk_value = config.get('min_chunk_value_usdt', 50)
        self.check_spread = config.get('check_spread', True)
        self.max_spread = config.get('max_spread_percent', 0.005)
        
        logger.info(f"TWAPExecutor initialized (chunks={self.default_num_chunks}, interval={self.default_interval}s)")
```

**Core Methods:**

#### 1.1 `should_use_twap(symbol, quantity, current_price)`
```python
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
    - Order size > X% of typical order book depth
    
    Args:
        symbol: Trading pair
        quantity: Order quantity
        current_price: Current market price
        
    Returns:
        True if TWAP recommended, False for direct execution
    """
    order_value = quantity * current_price
    
    # Use TWAP for orders > $1000
    if order_value > 1000:
        logger.info(
            f"TWAP recommended for {symbol}: "
            f"order_value=${order_value:.2f} > $1000"
        )
        return True
    
    return False
```

#### 1.2 `execute_twap(symbol, side, total_quantity, current_price, num_chunks, interval)`
```python
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
    num_chunks = num_chunks or self.default_num_chunks
    interval_seconds = interval_seconds or self.default_interval
    
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
    
    # Execution tracking
    start_time = time.time()
    orders = []
    total_filled = 0.0
    total_cost = 0.0  # For average price calculation
    total_fees = 0.0
    stopped_early = False
    stop_reason = None
    
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
            new_price = await self.exchange.get_price(symbol)
            price_deviation = abs(new_price - current_price) / current_price
            
            if price_deviation > self.max_price_deviation:
                logger.warning(
                    f"Price deviated {price_deviation*100:.2f}% from start, "
                    f"stopping TWAP"
                )
                stopped_early = True
                stop_reason = f"PRICE_DEVIATION: {price_deviation*100:.2f}%"
                break
            
            # Adjust chunk size for last chunk to account for rounding
            if chunk_index == num_chunks - 1:
                # Last chunk: fill remaining quantity
                remaining = total_quantity - total_filled
                chunk_size = self.precision_handler.round_quantity(symbol, remaining)
            
            # Execute chunk
            order = await self._execute_chunk(
                symbol=symbol,
                side=side,
                quantity=chunk_size,
                chunk_index=chunk_index
            )
            
            orders.append(order)
            
            # Update totals
            if order.status == 'FILLED' or order.status == 'PARTIALLY_FILLED':
                total_filled += order.filled_quantity
                total_cost += order.avg_fill_price * order.filled_quantity
                total_fees += order.fees
            
            logger.info(
                f"Chunk {chunk_index + 1} completed: "
                f"filled={order.filled_quantity}/{chunk_size}, "
                f"price={order.avg_fill_price:.2f}, "
                f"progress={total_filled}/{total_quantity}"
            )
            
            # Wait before next chunk (except for last chunk)
            if chunk_index < num_chunks - 1:
                logger.debug(f"Waiting {interval_seconds}s before next chunk")
                await asyncio.sleep(interval_seconds)
        
        except Exception as e:
            logger.error(f"Error executing chunk {chunk_index + 1}: {e}", exc_info=True)
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
    
    logger.info(
        f"TWAP execution complete: "
        f"filled={total_filled}/{total_quantity} ({total_filled/total_quantity*100:.1f}%), "
        f"avg_price={average_price:.2f}, "
        f"slippage={slippage_percent:+.2f}%, "
        f"time={execution_time:.1f}s, "
        f"stopped_early={stopped_early}"
    )
    
    return result
```

#### 1.3 `_execute_chunk(symbol, side, quantity, chunk_index)`
```python
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
        OrderExecutionError: If order fails
    """
    try:
        # Create market order
        response = await self.exchange.create_market_order(
            symbol=symbol,
            side=side,
            quantity=quantity
        )
        
        # Create order record
        order = Order(
            symbol=symbol,
            side=side,
            type='MARKET',
            quantity=quantity,
            status='SUBMITTED',
            exchange_order_id=response['orderId'],
            metadata={
                'twap_chunk': chunk_index,
                'execution_type': 'TWAP'
            }
        )
        
        # Wait for fill
        await self._wait_for_fill(order, timeout=30)
        
        return order
        
    except Exception as e:
        logger.error(f"Chunk execution failed: {e}")
        raise OrderExecutionError(f"Failed to execute chunk {chunk_index}: {e}")
```

#### 1.4 `_check_spread(symbol)`
```python
async def _check_spread(self, symbol: str) -> Tuple[bool, float]:
    """
    Check if current spread is acceptable.
    
    Args:
        symbol: Trading pair
        
    Returns:
        (spread_ok, spread_percent)
    """
    try:
        ob = await self.exchange.get_order_book(symbol, limit=5)
        
        best_bid = float(ob['bids'][0][0])
        best_ask = float(ob['asks'][0][0])
        
        spread_percent = (best_ask - best_bid) / best_bid
        
        spread_ok = spread_percent <= self.max_spread
        
        return spread_ok, spread_percent
        
    except Exception as e:
        logger.error(f"Error checking spread: {e}")
        # Default to OK on error (don't block execution)
        return True, 0.0
```

---

## 2. SIGNAL DEDUPLICATOR

### File: `src/execution/signal_deduplicator.py`

#### Class: `SignalDeduplicator`

**Purpose:** Prevent opening duplicate positions from the same signal generated multiple times.

**Problem:**
```
17:00 → Signal: BUY BTC/USDT @ 42000 (score 7.5)
17:01 → Same signal again! (market hasn't changed)
17:02 → Same signal again!

Without deduplication:
- 3 positions opened for same setup
- 3x risk
- Positions compete for same TP
```

**Solution:**
```
Generate unique signal ID based on:
- Symbol
- Side
- Entry price (rounded to avoid tiny differences)
- Timestamp bucket (5-minute window)

Cache recent signal IDs (last 10 minutes)
Reject duplicate IDs
```

**Constructor:**
```python
class SignalDeduplicator:
    """
    Prevent duplicate signal execution.
    
    Uses signal fingerprinting to detect duplicate signals
    within a time window.
    """
    
    def __init__(
        self,
        cache_ttl_seconds: int = 600,  # 10 minutes
        price_rounding_decimals: int = 0  # Round to nearest dollar
    ):
        """
        Initialize signal deduplicator.
        
        Args:
            cache_ttl_seconds: How long to remember signals (default: 600s = 10min)
            price_rounding_decimals: Price rounding for fingerprint (default: 0 = nearest dollar)
        """
        self.cache_ttl = cache_ttl_seconds
        self.price_rounding = price_rounding_decimals
        
        # Cache: {signal_id: timestamp}
        self.signal_cache: Dict[str, float] = {}
        
        logger.info(
            f"SignalDeduplicator initialized "
            f"(ttl={cache_ttl_seconds}s, price_rounding={price_rounding_decimals} decimals)"
        )
```

**Methods:**

#### 2.1 `generate_signal_id(signal)`
```python
def generate_signal_id(self, signal: Signal) -> str:
    """
    Generate unique fingerprint for signal.
    
    ID includes:
    - Symbol
    - Side
    - Entry price (rounded)
    - Timestamp bucket (5-minute buckets)
    
    Args:
        signal: Signal to fingerprint
        
    Returns:
        Signal ID string
        
    Example:
        Signal: BUY BTCUSDT @ 42150.75 at 17:03:22
        ID: "BTCUSDT_BUY_42151_17:00"
        
        Same signal at 17:04:30 would have same ID
        → Detected as duplicate!
    """
    # Round price
    rounded_price = round(signal.entry_price, self.price_rounding)
    
    # Timestamp bucket (5-minute)
    timestamp = signal.timestamp
    bucket_minutes = (timestamp.minute // 5) * 5  # 0, 5, 10, 15, ...
    time_bucket = timestamp.replace(minute=bucket_minutes, second=0, microsecond=0)
    
    # Generate ID
    signal_id = (
        f"{signal.symbol}_"
        f"{signal.side}_"
        f"{rounded_price:.{self.price_rounding}f}_"
        f"{time_bucket.strftime('%H:%M')}"
    )
    
    return signal_id
```

#### 2.2 `is_duplicate(signal)`
```python
def is_duplicate(self, signal: Signal) -> bool:
    """
    Check if signal is duplicate.
    
    Args:
        signal: Signal to check
        
    Returns:
        True if duplicate, False if new
    """
    # Clean expired entries first
    self._clean_expired()
    
    # Generate ID
    signal_id = self.generate_signal_id(signal)
    
    # Check cache
    if signal_id in self.signal_cache:
        cached_time = self.signal_cache[signal_id]
        age_seconds = time.time() - cached_time
        
        logger.warning(
            f"⚠️ DUPLICATE SIGNAL DETECTED: {signal_id} "
            f"(first seen {age_seconds:.0f}s ago)"
        )
        
        return True
    
    # New signal - add to cache
    self.signal_cache[signal_id] = time.time()
    
    logger.debug(f"New signal registered: {signal_id}")
    
    return False
```

#### 2.3 `_clean_expired()`
```python
def _clean_expired(self) -> None:
    """
    Remove expired entries from cache.
    
    Called before each duplicate check.
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
        logger.debug(f"Cleaned {len(expired_ids)} expired signal IDs from cache")
```

#### 2.4 `register_execution(signal)`
```python
def register_execution(self, signal: Signal) -> None:
    """
    Register that signal was executed.
    
    Updates cache timestamp to prevent near-duplicates.
    
    Args:
        signal: Signal that was executed
    """
    signal_id = self.generate_signal_id(signal)
    self.signal_cache[signal_id] = time.time()
    
    logger.debug(f"Signal execution registered: {signal_id}")
```

---

## 3. ORDER STATUS POLLER

### File: `src/execution/order_status_poller.py`

#### Class: `OrderStatusPoller`

**Purpose:** Monitor order fill status by polling exchange API.

**Why Needed:**
- After submitting order, need to know when it fills
- Can't assume instant fill (especially limit orders)
- Need to detect partial fills
- Need to detect rejections/cancellations

**Constructor:**
```python
class OrderStatusPoller:
    """
    Poll exchange for order status updates.
    
    Monitors orders until they reach terminal state (FILLED, CANCELED, REJECTED).
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
            exchange: Exchange client
            poll_interval_seconds: Time between status checks (default: 2.0s)
            default_timeout_seconds: Default timeout for polling (default: 30s)
        """
        self.exchange = exchange
        self.poll_interval = poll_interval_seconds
        self.default_timeout = default_timeout_seconds
        
        logger.info(
            f"OrderStatusPoller initialized "
            f"(interval={poll_interval_seconds}s, timeout={default_timeout_seconds}s)"
        )
```

**Methods:**

#### 3.1 `wait_for_fill(order, timeout)`
```python
async def wait_for_fill(
    self,
    order: Order,
    timeout: Optional[int] = None
) -> OrderFillResult:
    """
    Wait for order to fill (or fail).
    
    Polls order status until:
    - Order is FILLED
    - Order is PARTIALLY_FILLED (configurable if acceptable)
    - Order is CANCELED/REJECTED
    - Timeout reached
    
    Args:
        order: Order to monitor
        timeout: Max wait time in seconds (default: config value)
        
    Returns:
        OrderFillResult with:
        - status: Final status (FILLED, PARTIAL, FAILED, TIMEOUT)
        - filled_quantity: Quantity filled
        - avg_fill_price: Average fill price
        - fees: Trading fees paid
        - fill_time: Time when filled
        - polls_count: Number of status checks made
        
    Raises:
        OrderStatusError: If unable to check status
    """
    timeout = timeout or self.default_timeout
    start_time = time.time()
    polls_count = 0
    
    logger.info(
        f"Waiting for order {order.exchange_order_id} to fill "
        f"(timeout={timeout}s)"
    )
    
    while time.time() - start_time < timeout:
        polls_count += 1
        
        try:
            # Get order status from exchange
            status_data = await self.exchange.get_order_status(
                symbol=order.symbol,
                order_id=order.exchange_order_id
            )
            
            status = status_data['status']
            filled_qty = float(status_data['executedQty'])
            
            logger.debug(
                f"Order {order.exchange_order_id} status: {status}, "
                f"filled: {filled_qty}/{order.quantity}"
            )
            
            # Check terminal states
            if status == 'FILLED':
                # Fully filled
                result = OrderFillResult(
                    status='FILLED',
                    filled_quantity=filled_qty,
                    avg_fill_price=float(status_data['price']) if 'price' in status_data else float(status_data['avgPrice']),
                    fees=self._calculate_fees(status_data),
                    fill_time=datetime.fromtimestamp(status_data['updateTime'] / 1000),
                    polls_count=polls_count
                )
                
                logger.info(
                    f"✅ Order {order.exchange_order_id} FILLED: "
                    f"{filled_qty} @ {result.avg_fill_price:.2f}, "
                    f"polls={polls_count}"
                )
                
                return result
            
            elif status == 'PARTIALLY_FILLED':
                # Partially filled - decision point
                logger.warning(
                    f"⚠️ Order {order.exchange_order_id} PARTIALLY FILLED: "
                    f"{filled_qty}/{order.quantity}"
                )
                
                # For now, accept partial fills
                # TODO: Make this configurable
                result = OrderFillResult(
                    status='PARTIAL',
                    filled_quantity=filled_qty,
                    avg_fill_price=float(status_data.get('avgPrice', 0)),
                    fees=self._calculate_fees(status_data),
                    fill_time=datetime.now(),
                    polls_count=polls_count
                )
                
                return result
            
            elif status in ['CANCELED', 'REJECTED', 'EXPIRED']:
                # Order failed
                logger.error(
                    f"❌ Order {order.exchange_order_id} {status}: "
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
            
            # Still pending - wait and poll again
            await asyncio.sleep(self.poll_interval)
            
        except Exception as e:
            logger.error(f"Error polling order status: {e}")
            # Wait and retry
            await asyncio.sleep(self.poll_interval)
    
    # Timeout reached
    logger.error(
        f"⏱️ TIMEOUT waiting for order {order.exchange_order_id} "
        f"(waited {timeout}s, polls={polls_count})"
    )
    
    # Get final status
    try:
        status_data = await self.exchange.get_order_status(
            symbol=order.symbol,
            order_id=order.exchange_order_id
        )
        filled_qty = float(status_data['executedQty'])
    except:
        filled_qty = 0.0
    
    result = OrderFillResult(
        status='TIMEOUT',
        filled_quantity=filled_qty,
        avg_fill_price=0.0,
        fees=0.0,
        fill_time=datetime.now(),
        polls_count=polls_count
    )
    
    return result
```

#### 3.2 `_calculate_fees(status_data)`
```python
def _calculate_fees(self, status_data: dict) -> float:
    """
    Calculate trading fees from order status response.
    
    Args:
        status_data: Order status response from exchange
        
    Returns:
        Total fees in USDT
    """
    # Binance provides commission in fills array
    fills = status_data.get('fills', [])
    
    total_fees = 0.0
    
    for fill in fills:
        commission = float(fill.get('commission', 0))
        commission_asset = fill.get('commissionAsset', '')
        
        # If commission in USDT, add directly
        if commission_asset == 'USDT':
            total_fees += commission
        # If commission in other asset (e.g., BNB), convert to USDT
        # For simplicity, use default fee rate
        else:
            # Approximate: 0.1% of fill value
            fill_value = float(fill['price']) * float(fill['qty'])
            total_fees += fill_value * 0.001
    
    return total_fees
```

---

## 4. ORDER MANAGER ENHANCEMENTS

### File: `src/core/order_manager.py` (MODIFY)

#### Add: Partial Fill Handling

```python
class OrderManager:
    # ... existing code ...
    
    async def execute_order_with_twap_support(
        self,
        signal: Signal,
        quantity: float
    ) -> Order:
        """
        Execute order with automatic TWAP for large orders.
        
        Logic:
        1. Check if order should use TWAP
        2. If yes → Execute via TWAP
        3. If no → Execute as single market order
        4. Handle partial fills in both cases
        
        Args:
            signal: Trading signal
            quantity: Order quantity
            
        Returns:
            Primary order (or aggregated TWAP order)
        """
        symbol = signal.symbol
        side = signal.side
        current_price = signal.entry_price
        
        # Check if TWAP needed
        if self.twap_executor.should_use_twap(symbol, quantity, current_price):
            logger.info(f"Using TWAP execution for {symbol} (qty={quantity})")
            
            # Execute TWAP
            twap_result = await self.twap_executor.execute_twap(
                symbol=symbol,
                side=side,
                total_quantity=quantity,
                current_price=current_price
            )
            
            # Create aggregated order record
            order = Order(
                symbol=symbol,
                side=side,
                type='TWAP',
                quantity=quantity,
                filled_quantity=twap_result.total_filled,
                avg_fill_price=twap_result.average_price,
                status='FILLED' if twap_result.total_filled == quantity else 'PARTIALLY_FILLED',
                fees=twap_result.total_fees,
                metadata={
                    'execution_type': 'TWAP',
                    'chunks_executed': twap_result.chunks_executed,
                    'stopped_early': twap_result.stopped_early,
                    'stop_reason': twap_result.stop_reason
                }
            )
            
            await self.db.save_order(order)
            
            return order
        
        else:
            # Single market order
            logger.info(f"Using direct market order for {symbol} (qty={quantity})")
            
            return await self._execute_market_order(symbol, side, quantity)
    
    async def _execute_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float
    ) -> Order:
        """
        Execute single market order with fill monitoring.
        
        Args:
            symbol: Trading pair
            side: BUY or SELL
            quantity: Order quantity
            
        Returns:
            Filled order
        """
        # Round to exchange precision
        quantity = self.precision_handler.round_quantity(symbol, quantity)
        
        # Submit order
        response = await self.exchange.create_market_order(
            symbol=symbol,
            side=side,
            quantity=quantity
        )
        
        # Create order record
        order = Order(
            symbol=symbol,
            side=side,
            type='MARKET',
            quantity=quantity,
            status='SUBMITTED',
            exchange_order_id=response['orderId']
        )
        
        await self.db.save_order(order)
        
        # Wait for fill
        fill_result = await self.order_status_poller.wait_for_fill(
            order,
            timeout=30
        )
        
        # Update order with fill result
        order.filled_quantity = fill_result.filled_quantity
        order.avg_fill_price = fill_result.avg_fill_price
        order.fees = fill_result.fees
        order.status = fill_result.status
        
        await self.db.update_order(order)
        
        # Handle partial fill
        if fill_result.status == 'PARTIAL':
            await self._handle_partial_fill(order, fill_result)
        
        return order
    
    async def _handle_partial_fill(
        self,
        order: Order,
        fill_result: OrderFillResult
    ) -> None:
        """
        Handle partially filled order.
        
        Options:
        1. Cancel remaining quantity
        2. Wait for full fill
        3. Accept partial and adjust position
        
        Current implementation: Accept partial and adjust
        
        Args:
            order: Partially filled order
            fill_result: Fill result
        """
        filled_percent = (fill_result.filled_quantity / order.quantity) * 100
        
        logger.warning(
            f"Partial fill: {order.symbol} "
            f"filled={fill_result.filled_quantity}/{order.quantity} ({filled_percent:.1f}%)"
        )
        
        # Strategy: Accept partial fill
        # Position will be created with filled_quantity, not requested quantity
        # Risk calculation already done on requested quantity, so partial is safer
        
        # Send alert
        await self.alert_manager.send_alert(
            level='WARNING',
            message=f"Partial fill: {order.symbol} {filled_percent:.1f}% filled",
            data={
                'order_id': order.id,
                'requested': order.quantity,
                'filled': fill_result.filled_quantity
            }
        )
```

---

## 📋 TEST SPECIFICATIONS

### File: `tests/unit/test_twap_executor.py`

```python
import pytest
from unittest.mock import Mock, AsyncMock
from src.execution.twap_executor import TWAPExecutor


class TestTWAPExecutor:
    @pytest.fixture
    def executor(self):
        exchange = Mock()
        precision_handler = Mock()
        config = {
            'default_num_chunks': 5,
            'default_interval_seconds': 1,  # Fast for testing
            'max_price_deviation_percent': 0.01,
            'min_chunk_value_usdt': 50
        }
        return TWAPExecutor(exchange, precision_handler, config)
    
    def test_should_use_twap_large_order(self, executor):
        """Test TWAP recommended for large order"""
        result = executor.should_use_twap(
            symbol='BTCUSDT',
            quantity=0.5,  # 0.5 BTC
            current_price=42000.0  # $21,000 value
        )
        assert result == True
    
    def test_should_not_use_twap_small_order(self, executor):
        """Test TWAP not needed for small order"""
        result = executor.should_use_twap(
            symbol='BTCUSDT',
            quantity=0.01,  # 0.01 BTC
            current_price=42000.0  # $420 value
        )
        assert result == False
    
    @pytest.mark.asyncio
    async def test_execute_twap_splits_correctly(self, executor):
        """Test TWAP splits order into chunks"""
        executor.exchange.create_market_order = AsyncMock()
        executor.exchange.get_price = AsyncMock(return_value=42000.0)
        executor.exchange.get_order_status = AsyncMock(return_value={
            'status': 'FILLED',
            'executedQty': '0.1',
            'price': '42000.0',
            'updateTime': 1640000000000,
            'fills': []
        })
        executor.precision_handler.round_quantity = Mock(side_effect=lambda s, q: q)
        
        result = await executor.execute_twap(
            symbol='BTCUSDT',
            side='BUY',
            total_quantity=0.5,
            current_price=42000.0,
            num_chunks=5,
            interval_seconds=0.1  # Fast for testing
        )
        
        assert result.chunks_executed == 5
        assert result.total_filled == 0.5
    
    @pytest.mark.asyncio
    async def test_twap_stops_on_price_deviation(self, executor):
        """Test TWAP stops if price moves too much"""
        call_count = 0
        
        async def mock_get_price(symbol):
            nonlocal call_count
            call_count += 1
            # First call: 42000, second call: 42500 (big jump!)
            return 42000.0 if call_count == 1 else 42500.0
        
        executor.exchange.get_price = mock_get_price
        executor.exchange.create_market_order = AsyncMock()
        executor.precision_handler.round_quantity = Mock(side_effect=lambda s, q: q)
        
        result = await executor.execute_twap(
            symbol='BTCUSDT',
            side='BUY',
            total_quantity=0.5,
            current_price=42000.0,
            num_chunks=5,
            interval_seconds=0.1
        )
        
        assert result.stopped_early == True
        assert 'PRICE_DEVIATION' in result.stop_reason
```

### File: `tests/unit/test_signal_deduplicator.py`

```python
import pytest
from datetime import datetime, timedelta
from src.execution.signal_deduplicator import SignalDeduplicator
from src.models.signal import Signal


class TestSignalDeduplicator:
    @pytest.fixture
    def deduplicator(self):
        return SignalDeduplicator(
            cache_ttl_seconds=600,
            price_rounding_decimals=0
        )
    
    def test_generate_signal_id(self, deduplicator):
        """Test signal ID generation"""
        signal = Signal(
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42150.75,
            timestamp=datetime(2025, 1, 28, 17, 3, 22)
        )
        
        signal_id = deduplicator.generate_signal_id(signal)
        
        # Should round price and bucket time
        assert signal_id == 'BTCUSDT_BUY_42151_17:00'
    
    def test_is_duplicate_detects_same_signal(self, deduplicator):
        """Test duplicate detection"""
        signal1 = Signal(
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42150.0,
            timestamp=datetime(2025, 1, 28, 17, 3, 0)
        )
        
        signal2 = Signal(
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42149.0,  # Slightly different but rounds same
            timestamp=datetime(2025, 1, 28, 17, 4, 30)  # Same bucket
        )
        
        # First signal
        is_dup1 = deduplicator.is_duplicate(signal1)
        assert is_dup1 == False
        
        # Second signal (duplicate!)
        is_dup2 = deduplicator.is_duplicate(signal2)
        assert is_dup2 == True
    
    def test_different_signals_not_duplicate(self, deduplicator):
        """Test different signals not flagged as duplicate"""
        signal1 = Signal(
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42000.0,
            timestamp=datetime.now()
        )
        
        signal2 = Signal(
            symbol='ETHUSDT',  # Different symbol
            side='BUY',
            entry_price=2200.0,
            timestamp=datetime.now()
        )
        
        is_dup1 = deduplicator.is_duplicate(signal1)
        is_dup2 = deduplicator.is_duplicate(signal2)
        
        assert is_dup1 == False
        assert is_dup2 == False
```

---

## 🚀 CURSOR PROMPTS

### Prompt 1: Create TWAP Executor

```
Create src/execution/twap_executor.py implementing TWAPExecutor class.

Read the specification in WEEK1_DAY3-4_SPEC.md (TWAP Executor section).

Requirements:
1. Implement execute_twap() method that splits orders into chunks
2. Execute chunks with time intervals
3. Monitor price deviation and stop if exceeded
4. Check spread before each chunk
5. Handle errors gracefully (stop early if needed)
6. Return comprehensive TWAPResult

Critical logic:
- Calculate chunk size (total_quantity / num_chunks)
- Execute each chunk as market order
- Wait interval_seconds between chunks
- Stop early if price deviates > threshold
- Stop early if spread widens > threshold
- Track total filled, average price, fees, slippage

This prevents excessive slippage on large orders - must work correctly!
```

### Prompt 2: Create Signal Deduplicator

```
Create src/execution/signal_deduplicator.py implementing SignalDeduplicator class.

Read specification in WEEK1_DAY3-4_SPEC.md (Signal Deduplicator section).

Requirements:
1. Generate signal fingerprint (ID) from symbol, side, price, time
2. Cache signal IDs with timestamps
3. Check if signal is duplicate
4. Clean expired entries from cache
5. Round price to avoid tiny differences causing false negatives
6. Use 5-minute time buckets

Critical logic:
- generate_signal_id(): Create unique ID with rounded price and time bucket
- is_duplicate(): Check cache and return True/False
- _clean_expired(): Remove old entries (> ttl)

This prevents opening 3 positions from same signal - critical for risk management!
```

### Prompt 3: Create Order Status Poller

```
Create src/execution/order_status_poller.py implementing OrderStatusPoller class.

Read specification in WEEK1_DAY3-4_SPEC.md (Order Status Poller section).

Requirements:
1. Poll exchange for order status
2. Wait until order FILLED, CANCELED, or timeout
3. Handle partial fills
4. Calculate fees from fills array
5. Return OrderFillResult with all details

Critical logic:
- Poll every 2 seconds
- Check status: FILLED, PARTIALLY_FILLED, CANCELED, REJECTED
- For FILLED: extract avg price, fees, update time
- For PARTIAL: return with filled quantity
- For failed: return with failure reason
- On timeout: return timeout status with what was filled

Reliable order monitoring is essential - can't assume instant fills!
```

### Prompt 4: Enhance Order Manager

```
Modify src/core/order_manager.py to add TWAP support and partial fill handling.

Read specification in WEEK1_DAY3-4_SPEC.md (Order Manager Enhancements section).

Add these methods:
1. execute_order_with_twap_support(signal, quantity)
   - Check if TWAP needed
   - Route to TWAP or direct execution
   
2. _execute_market_order(symbol, side, quantity)
   - Execute single market order
   - Use OrderStatusPoller to wait for fill
   - Update order with fill result
   
3. _handle_partial_fill(order, fill_result)
   - Log partial fill warning
   - Send alert
   - Accept partial (don't cancel remaining)

Integration:
- Use self.twap_executor
- Use self.order_status_poller
- Create Order records for all executions
- Handle both TWAP and direct orders

This routes large orders through TWAP automatically - critical for slippage reduction!
```

### Prompt 5: Create Tests

```
Create comprehensive unit tests:

1. tests/unit/test_twap_executor.py
   - Test TWAP splits correctly
   - Test stops on price deviation
   - Test stops on wide spread
   - Mock exchange responses

2. tests/unit/test_signal_deduplicator.py
   - Test signal ID generation
   - Test duplicate detection
   - Test different signals pass
   - Test expiry cleanup

3. tests/unit/test_order_status_poller.py
   - Test waits for fill
   - Test detects partial fill
   - Test handles timeout
   - Test calculates fees

Use pytest, pytest-asyncio, and mocks.
Aim for 90%+ coverage.
```

---

## ✅ ACCEPTANCE CRITERIA

Day 3-4 complete when:

```
Code:
□ TWAPExecutor class created (350+ lines)
□ SignalDeduplicator class created (150+ lines)
□ OrderStatusPoller class created (200+ lines)
□ OrderManager enhanced with TWAP support
□ All type hints present
□ All docstrings present
□ Comprehensive error handling

Tests:
□ test_twap_executor.py (10+ tests)
□ test_signal_deduplicator.py (8+ tests)
□ test_order_status_poller.py (8+ tests)
□ All tests passing
□ 90%+ coverage

Integration:
□ Can execute TWAP order end-to-end
□ Can detect duplicate signals
□ Can monitor order fills
□ No import errors

Validation:
□ pytest tests/unit/test_twap_executor.py -v
□ pytest tests/unit/test_signal_deduplicator.py -v
□ pytest tests/unit/test_order_status_poller.py -v
□ All GREEN
```

---

## 📊 ESTIMATED TIME

- TWAP Executor: 5-6 hours
- Signal Deduplicator: 2-3 hours
- Order Status Poller: 3-4 hours
- Order Manager Enhancement: 2-3 hours
- Unit Tests: 4-5 hours
- Integration & Testing: 2-3 hours

**Total: 18-24 hours (2 days)**

---

**READY FOR DAY 3-4! 🚀**