# 📋 WEEK 1 - DAY 1-2 DETAILED SPECIFICATION
## Position Monitoring & Emergency Controls

**Duration:** 2 days  
**Priority:** CRITICAL ❌  
**Dependencies:** None (highest priority)

---

## 🎯 OBJECTIVES

1. **Position Monitor:** Real-time SL/TP checking (every 5 seconds)
2. **Emergency Controller:** Kill switch and emergency position closure
3. **Position Close Logic:** Proper position closure with PnL calculation

**Why Critical:** Without this, stop-losses never trigger → unlimited losses

---

## 📂 FILES TO CREATE

```
src/core/
├── position_monitor.py          (NEW - 300 lines)
├── emergency_controller.py       (NEW - 200 lines)
└── order_manager.py             (MODIFY - add close_position method)

tests/unit/
├── test_position_monitor.py     (NEW - 150 lines)
└── test_emergency_controller.py (NEW - 100 lines)

tests/integration/
└── test_monitoring_integration.py (NEW - 200 lines)
```

---

## 📝 DETAILED SPECIFICATIONS

---

## 1. POSITION MONITOR

### File: `src/core/position_monitor.py`

#### Class: `PositionMonitor`

**Purpose:** Continuously monitor all open positions and trigger SL/TP when price reaches threshold.

**Responsibilities:**
1. Check stop-loss every 5 seconds
2. Check take-profit every 5 seconds
3. Update trailing stops
4. Monitor position age
5. Detect adverse market conditions
6. Close positions automatically when needed

**Constructor:**
```python
class PositionMonitor:
    """Real-time position monitoring with automatic SL/TP execution"""
    
    def __init__(
        self,
        position_manager: PositionManager,
        order_manager: OrderManager,
        exchange: BinanceExchange,
        alert_manager: AlertManager,
        config: dict
    ):
        """
        Initialize position monitor.
        
        Args:
            position_manager: Position data access
            order_manager: For closing positions
            exchange: Price data source
            alert_manager: For sending alerts
            config: Configuration dict with:
                - check_interval: Seconds between checks (default: 5)
                - trailing_stop_enabled: Enable trailing stops (default: False)
                - max_position_age_hours: Max hold time (default: None)
                - adverse_spread_threshold: Close if spread > threshold (default: 0.5%)
        """
        self.position_manager = position_manager
        self.order_manager = order_manager
        self.exchange = exchange
        self.alert_manager = alert_manager
        
        self.check_interval = config.get('check_interval', 5)
        self.trailing_stop_enabled = config.get('trailing_stop_enabled', False)
        self.max_position_age_hours = config.get('max_position_age_hours', None)
        self.adverse_spread_threshold = config.get('adverse_spread_threshold', 0.005)
        
        self.running = False
        self.monitor_task: Optional[asyncio.Task] = None
        
        logger.info(f"PositionMonitor initialized (check_interval={self.check_interval}s)")
```

**Main Methods:**

#### 1.1 `start()`
```python
async def start(self) -> None:
    """
    Start position monitoring loop.
    
    Creates asyncio task that runs monitor_positions() continuously.
    """
    if self.running:
        logger.warning("Position monitor already running")
        return
    
    self.running = True
    self.monitor_task = asyncio.create_task(self._monitor_loop())
    logger.info("Position monitor started")
```

#### 1.2 `stop()`
```python
async def stop(self) -> None:
    """
    Stop position monitoring loop.
    
    Cancels monitoring task gracefully.
    """
    if not self.running:
        return
    
    self.running = False
    if self.monitor_task:
        self.monitor_task.cancel()
        try:
            await self.monitor_task
        except asyncio.CancelledError:
            pass
    
    logger.info("Position monitor stopped")
```

#### 1.3 `_monitor_loop()` (CORE LOGIC)
```python
async def _monitor_loop(self) -> None:
    """
    Main monitoring loop - runs continuously.
    
    Logic:
    1. Get all open positions
    2. For each position:
        a. Get current price
        b. Check stop-loss
        c. Check take-profit
        d. Check trailing stop
        e. Check adverse conditions
        f. Check age limit
    3. Sleep for check_interval seconds
    4. Repeat
    
    Error Handling:
    - Individual position errors logged but don't stop loop
    - Critical errors logged and re-raised
    """
    logger.info("Position monitoring loop started")
    
    while self.running:
        try:
            # Get all open positions
            positions = await self.position_manager.get_open_positions()
            
            if not positions:
                logger.debug("No open positions to monitor")
            else:
                logger.debug(f"Monitoring {len(positions)} positions")
                
                # Check each position
                for position in positions:
                    try:
                        await self._check_position(position)
                    except Exception as e:
                        logger.error(
                            f"Error monitoring position {position.id}: {e}",
                            exc_info=True
                        )
                        # Continue with other positions
            
            # Sleep before next check
            await asyncio.sleep(self.check_interval)
            
        except asyncio.CancelledError:
            logger.info("Monitoring loop cancelled")
            break
        except Exception as e:
            logger.error(f"Critical error in monitoring loop: {e}", exc_info=True)
            # Sleep and retry
            await asyncio.sleep(self.check_interval)
```

#### 1.4 `_check_position(position)` (CRITICAL)
```python
async def _check_position(self, position: Position) -> None:
    """
    Check single position for exit conditions.
    
    Exit conditions checked (in order):
    1. Stop-loss hit
    2. Take-profit hit
    3. Trailing stop hit
    4. Max age exceeded
    5. Adverse market conditions
    
    Args:
        position: Position to check
    """
    symbol = position.symbol
    
    # Get current price
    try:
        current_price = await self.exchange.get_price(symbol)
    except Exception as e:
        logger.error(f"Failed to get price for {symbol}: {e}")
        return
    
    logger.debug(
        f"Checking position {position.id}: {symbol} "
        f"current={current_price:.2f} SL={position.stop_loss:.2f} TP={position.take_profit:.2f}"
    )
    
    # 1. Check Stop-Loss
    if await self._check_stop_loss(position, current_price):
        await self._close_position_with_reason(
            position,
            reason="STOP_LOSS_HIT",
            current_price=current_price
        )
        return
    
    # 2. Check Take-Profit
    if await self._check_take_profit(position, current_price):
        await self._close_position_with_reason(
            position,
            reason="TAKE_PROFIT_HIT",
            current_price=current_price
        )
        return
    
    # 3. Update Trailing Stop (if enabled)
    if self.trailing_stop_enabled:
        await self._update_trailing_stop(position, current_price)
    
    # 4. Check Max Age
    if self.max_position_age_hours:
        age_hours = (datetime.now() - position.opened_at).total_seconds() / 3600
        if age_hours > self.max_position_age_hours:
            logger.info(
                f"Position {position.id} exceeded max age "
                f"({age_hours:.1f}h > {self.max_position_age_hours}h)"
            )
            await self._close_position_with_reason(
                position,
                reason="MAX_AGE_EXCEEDED",
                current_price=current_price
            )
            return
    
    # 5. Check Adverse Conditions
    if await self._check_adverse_conditions(position, current_price):
        await self._close_position_with_reason(
            position,
            reason="ADVERSE_CONDITIONS",
            current_price=current_price
        )
        return
```

#### 1.5 `_check_stop_loss(position, current_price)`
```python
async def _check_stop_loss(
    self,
    position: Position,
    current_price: float
) -> bool:
    """
    Check if stop-loss should trigger.
    
    Logic:
    - LONG position: current_price <= stop_loss
    - SHORT position: current_price >= stop_loss
    
    Args:
        position: Position to check
        current_price: Current market price
        
    Returns:
        True if stop-loss hit, False otherwise
    """
    if position.side == 'BUY':
        # Long position: price dropped to or below SL
        if current_price <= position.stop_loss:
            logger.warning(
                f"⚠️ STOP-LOSS HIT: {position.symbol} "
                f"price {current_price:.2f} <= SL {position.stop_loss:.2f}"
            )
            return True
    
    elif position.side == 'SELL':
        # Short position: price rose to or above SL
        if current_price >= position.stop_loss:
            logger.warning(
                f"⚠️ STOP-LOSS HIT: {position.symbol} "
                f"price {current_price:.2f} >= SL {position.stop_loss:.2f}"
            )
            return True
    
    return False
```

#### 1.6 `_check_take_profit(position, current_price)`
```python
async def _check_take_profit(
    self,
    position: Position,
    current_price: float
) -> bool:
    """
    Check if take-profit should trigger.
    
    Logic:
    - LONG position: current_price >= take_profit
    - SHORT position: current_price <= take_profit
    
    Args:
        position: Position to check
        current_price: Current market price
        
    Returns:
        True if take-profit hit, False otherwise
    """
    if position.take_profit is None:
        return False
    
    if position.side == 'BUY':
        # Long position: price rose to or above TP
        if current_price >= position.take_profit:
            logger.info(
                f"✅ TAKE-PROFIT HIT: {position.symbol} "
                f"price {current_price:.2f} >= TP {position.take_profit:.2f}"
            )
            return True
    
    elif position.side == 'SELL':
        # Short position: price dropped to or below TP
        if current_price <= position.take_profit:
            logger.info(
                f"✅ TAKE-PROFIT HIT: {position.symbol} "
                f"price {current_price:.2f} <= TP {position.take_profit:.2f}"
            )
            return True
    
    return False
```

#### 1.7 `_update_trailing_stop(position, current_price)`
```python
async def _update_trailing_stop(
    self,
    position: Position,
    current_price: float
) -> None:
    """
    Update trailing stop-loss.
    
    Logic:
    - Track maximum favorable price (max_price for LONG, min_price for SHORT)
    - Move stop-loss to follow price at fixed distance
    - Never move stop-loss in unfavorable direction
    
    Example (LONG):
    - Entry: $100, SL: $98 (2% below)
    - Price moves to $105 → New SL: $102.90 (2% below $105)
    - Price drops to $103 → SL stays at $102.90 (doesn't move down)
    
    Args:
        position: Position to update
        current_price: Current market price
    """
    if position.trailing_stop_percent is None:
        return
    
    if position.side == 'BUY':
        # Long position: track max price
        if position.max_price is None or current_price > position.max_price:
            position.max_price = current_price
            
            # Calculate new stop-loss
            new_stop = position.max_price * (1 - position.trailing_stop_percent)
            
            # Only update if new stop is higher than current
            if new_stop > position.stop_loss:
                old_stop = position.stop_loss
                position.stop_loss = new_stop
                
                await self.position_manager.update_position(position)
                
                logger.info(
                    f"📈 Trailing stop updated: {position.symbol} "
                    f"SL {old_stop:.2f} → {new_stop:.2f} "
                    f"(max_price={position.max_price:.2f})"
                )
    
    elif position.side == 'SELL':
        # Short position: track min price
        if position.min_price is None or current_price < position.min_price:
            position.min_price = current_price
            
            # Calculate new stop-loss
            new_stop = position.min_price * (1 + position.trailing_stop_percent)
            
            # Only update if new stop is lower than current
            if new_stop < position.stop_loss:
                old_stop = position.stop_loss
                position.stop_loss = new_stop
                
                await self.position_manager.update_position(position)
                
                logger.info(
                    f"📉 Trailing stop updated: {position.symbol} "
                    f"SL {old_stop:.2f} → {new_stop:.2f} "
                    f"(min_price={position.min_price:.2f})"
                )
```

#### 1.8 `_check_adverse_conditions(position, current_price)`
```python
async def _check_adverse_conditions(
    self,
    position: Position,
    current_price: float
) -> bool:
    """
    Check for adverse market conditions that warrant closing position.
    
    Conditions checked:
    1. Spread widened significantly (> threshold)
    2. Liquidity dried up (order book depth too low)
    
    Args:
        position: Position to check
        current_price: Current market price
        
    Returns:
        True if adverse conditions detected, False otherwise
    """
    try:
        # Get current order book
        ob = await self.exchange.get_order_book(position.symbol, limit=20)
        
        # Check spread
        best_bid = float(ob['bids'][0][0])
        best_ask = float(ob['asks'][0][0])
        spread_percent = (best_ask - best_bid) / best_bid
        
        if spread_percent > self.adverse_spread_threshold:
            logger.warning(
                f"⚠️ Wide spread detected: {position.symbol} "
                f"spread={spread_percent*100:.2f}% > threshold={self.adverse_spread_threshold*100:.2f}%"
            )
            return True
        
        # Check liquidity (top 10 levels)
        bid_liquidity = sum([float(b[1]) for b in ob['bids'][:10]])
        ask_liquidity = sum([float(a[1]) for a in ob['asks'][:10]])
        total_liquidity_usdt = (bid_liquidity + ask_liquidity) * current_price / 2
        
        if total_liquidity_usdt < 10000:  # Less than $10k liquidity
            logger.warning(
                f"⚠️ Low liquidity detected: {position.symbol} "
                f"liquidity={total_liquidity_usdt:.0f} USDT"
            )
            return True
        
    except Exception as e:
        logger.error(f"Error checking adverse conditions: {e}")
        # Don't close on error
        return False
    
    return False
```

#### 1.9 `_close_position_with_reason(position, reason, current_price)`
```python
async def _close_position_with_reason(
    self,
    position: Position,
    reason: str,
    current_price: float
) -> None:
    """
    Close position and log reason.
    
    Args:
        position: Position to close
        reason: Closure reason (STOP_LOSS_HIT, TAKE_PROFIT_HIT, etc)
        current_price: Price at closure
    """
    logger.info(
        f"Closing position {position.id} ({position.symbol}): {reason}"
    )
    
    try:
        # Close position via order manager
        exit_order = await self.order_manager.close_position(
            position=position,
            reason=reason,
            current_price=current_price
        )
        
        # Send alert
        await self.alert_manager.send_alert(
            level='INFO',
            message=f"Position closed: {position.symbol} - {reason}",
            data={
                'position_id': position.id,
                'symbol': position.symbol,
                'entry_price': position.entry_price,
                'exit_price': current_price,
                'pnl': exit_order.pnl if hasattr(exit_order, 'pnl') else None,
                'reason': reason
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to close position {position.id}: {e}", exc_info=True)
        
        # Send error alert
        await self.alert_manager.send_alert(
            level='ERROR',
            message=f"Failed to close position: {position.symbol}",
            data={'error': str(e), 'position_id': position.id}
        )
```

---

## 2. EMERGENCY CONTROLLER

### File: `src/core/emergency_controller.py`

#### Class: `EmergencyController`

**Purpose:** Provide emergency controls for crisis situations (kill switch, close all positions).

**Constructor:**
```python
class EmergencyController:
    """Emergency controls for crisis situations"""
    
    def __init__(
        self,
        position_manager: PositionManager,
        order_manager: OrderManager,
        alert_manager: AlertManager,
        config: dict
    ):
        """
        Initialize emergency controller.
        
        Args:
            position_manager: Position data access
            order_manager: For closing positions
            alert_manager: For sending critical alerts
            config: Configuration dict with:
                - max_daily_loss_percent: Trigger at daily loss (default: 0.05)
                - max_single_position_loss_percent: Trigger on big loss (default: 0.10)
                - kill_switch_file: File path to check (default: /tmp/KILL_SWITCH)
        """
        self.position_manager = position_manager
        self.order_manager = order_manager
        self.alert_manager = alert_manager
        
        self.max_daily_loss = config.get('max_daily_loss_percent', 0.05)
        self.max_single_loss = config.get('max_single_position_loss_percent', 0.10)
        self.kill_switch_file = config.get('kill_switch_file', '/tmp/KILL_SWITCH')
        
        self.emergency_mode = False
        self.trading_paused = False
        
        logger.info("EmergencyController initialized")
```

**Methods:**

#### 2.1 `check_emergency_triggers(portfolio)`
```python
async def check_emergency_triggers(self, portfolio: Portfolio) -> bool:
    """
    Check if emergency conditions met.
    
    Triggers:
    1. Daily loss exceeds threshold
    2. Single position loss exceeds threshold
    3. Kill switch file exists
    
    Args:
        portfolio: Portfolio to check
        
    Returns:
        True if emergency triggered, False otherwise
    """
    # Check daily loss
    daily_pnl_percent = portfolio.get_daily_pnl_percent()
    if daily_pnl_percent < -self.max_daily_loss:
        logger.critical(
            f"🚨 EMERGENCY: Daily loss {daily_pnl_percent:.2f}% exceeds "
            f"threshold -{self.max_daily_loss*100:.2f}%"
        )
        await self.trigger_emergency_stop(
            reason=f"Daily loss {daily_pnl_percent:.2f}%"
        )
        return True
    
    # Check single position loss
    positions = await self.position_manager.get_open_positions()
    for position in positions:
        current_price = await self.exchange.get_price(position.symbol)
        pnl_percent = self._calculate_pnl_percent(position, current_price)
        
        if pnl_percent < -self.max_single_loss:
            logger.critical(
                f"🚨 EMERGENCY: Position {position.symbol} loss {pnl_percent:.2f}% "
                f"exceeds threshold -{self.max_single_loss*100:.2f}%"
            )
            await self.trigger_emergency_stop(
                reason=f"Position {position.symbol} loss {pnl_percent:.2f}%"
            )
            return True
    
    # Check kill switch file
    if os.path.exists(self.kill_switch_file):
        logger.critical(f"🚨 EMERGENCY: Kill switch file detected at {self.kill_switch_file}")
        await self.trigger_emergency_stop(reason="Kill switch file")
        return True
    
    return False
```

#### 2.2 `trigger_emergency_stop(reason)`
```python
async def trigger_emergency_stop(self, reason: str) -> None:
    """
    Trigger emergency stop - close all positions immediately.
    
    Actions:
    1. Set emergency mode flag
    2. Send critical alert
    3. Close all open positions
    4. Pause trading
    5. Log event
    
    Args:
        reason: Reason for emergency stop
    """
    if self.emergency_mode:
        logger.warning("Emergency stop already in progress")
        return
    
    self.emergency_mode = True
    
    logger.critical(f"🚨🚨🚨 EMERGENCY STOP TRIGGERED: {reason} 🚨🚨🚨")
    
    # Send critical alert
    await self.alert_manager.send_alert(
        level='CRITICAL',
        message=f"🚨 EMERGENCY STOP: {reason}",
        data={'timestamp': datetime.now().isoformat()}
    )
    
    # Close all positions
    try:
        await self.close_all_positions(reason=f"EMERGENCY: {reason}")
    except Exception as e:
        logger.error(f"Error closing positions during emergency: {e}", exc_info=True)
    
    # Pause trading
    self.trading_paused = True
    
    logger.critical("Emergency stop completed")
```

#### 2.3 `close_all_positions(reason)`
```python
async def close_all_positions(self, reason: str = "MANUAL") -> Dict[str, any]:
    """
    Close all open positions immediately.
    
    Uses market orders for immediate execution.
    
    Args:
        reason: Closure reason
        
    Returns:
        Dict with:
        - positions_closed: Number of positions closed
        - failed_closures: List of positions that failed to close
        - total_pnl: Total PnL from closures
    """
    positions = await self.position_manager.get_open_positions()
    
    if not positions:
        logger.info("No open positions to close")
        return {
            'positions_closed': 0,
            'failed_closures': [],
            'total_pnl': 0.0
        }
    
    logger.warning(f"Closing {len(positions)} positions (reason: {reason})")
    
    closed_count = 0
    failed = []
    total_pnl = 0.0
    
    # Close positions concurrently
    tasks = []
    for position in positions:
        task = self.order_manager.close_position(
            position=position,
            reason=reason,
            emergency=True
        )
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for position, result in zip(positions, results):
        if isinstance(result, Exception):
            logger.error(f"Failed to close position {position.id}: {result}")
            failed.append({
                'position_id': position.id,
                'symbol': position.symbol,
                'error': str(result)
            })
        else:
            closed_count += 1
            if hasattr(result, 'pnl'):
                total_pnl += result.pnl
            logger.info(f"Closed position {position.id} ({position.symbol})")
    
    summary = {
        'positions_closed': closed_count,
        'failed_closures': failed,
        'total_pnl': total_pnl
    }
    
    logger.warning(
        f"Position closure complete: {closed_count}/{len(positions)} closed, "
        f"PnL: ${total_pnl:.2f}"
    )
    
    return summary
```

#### 2.4 `pause_trading()` & `resume_trading()`
```python
async def pause_trading(self) -> None:
    """
    Pause new position opening (keep existing positions).
    """
    if self.trading_paused:
        logger.warning("Trading already paused")
        return
    
    self.trading_paused = True
    logger.warning("🟡 Trading paused - no new positions will be opened")
    
    await self.alert_manager.send_alert(
        level='WARNING',
        message="Trading paused"
    )

async def resume_trading(self) -> None:
    """
    Resume trading after pause.
    """
    if not self.trading_paused:
        logger.info("Trading already active")
        return
    
    self.trading_paused = False
    self.emergency_mode = False
    logger.info("🟢 Trading resumed")
    
    await self.alert_manager.send_alert(
        level='INFO',
        message="Trading resumed"
    )
```

---

## 3. ORDER MANAGER ENHANCEMENT

### File: `src/core/order_manager.py` (MODIFY)

#### Add Method: `close_position(position, reason, emergency, current_price)`

```python
async def close_position(
    self,
    position: Position,
    reason: str,
    emergency: bool = False,
    current_price: Optional[float] = None
) -> Order:
    """
    Close position with market order.
    
    Steps:
    1. Get current price (if not provided)
    2. Create opposite side market order
    3. Execute order
    4. Wait for fill
    5. Calculate PnL
    6. Update position status
    7. Create trade record
    8. Send alert
    
    Args:
        position: Position to close
        reason: Closure reason (STOP_LOSS_HIT, TAKE_PROFIT_HIT, MANUAL, etc)
        emergency: If True, skip some validations for speed
        current_price: Optional current price (to avoid extra API call)
        
    Returns:
        Exit order
        
    Raises:
        OrderExecutionError: If order execution fails
    """
    symbol = position.symbol
    
    logger.info(
        f"Closing position {position.id} ({symbol}): {reason} "
        f"(emergency={emergency})"
    )
    
    # Get current price
    if current_price is None:
        current_price = await self.exchange.get_price(symbol)
    
    # Determine exit side (opposite of entry)
    exit_side = 'SELL' if position.side == 'BUY' else 'BUY'
    
    # Quantity to close
    quantity = position.quantity
    
    # Round quantity to exchange precision
    quantity = self.precision_handler.round_quantity(symbol, quantity)
    
    # Create market order
    logger.debug(
        f"Creating market order: {exit_side} {quantity} {symbol} @ market"
    )
    
    try:
        # Execute market order
        response = await self.exchange.create_market_order(
            symbol=symbol,
            side=exit_side,
            quantity=quantity
        )
        
        # Create order record
        exit_order = Order(
            symbol=symbol,
            side=exit_side,
            type='MARKET',
            quantity=quantity,
            price=None,  # Market order
            status='SUBMITTED',
            exchange_order_id=response['orderId'],
            position_id=position.id,
            metadata={
                'closure_reason': reason,
                'emergency': emergency
            }
        )
        
        await self.db.save_order(exit_order)
        
        # Wait for fill
        filled = await self._wait_for_fill(
            exit_order,
            timeout=10 if emergency else 30
        )
        
        if not filled:
            raise OrderExecutionError(f"Order {exit_order.id} timed out")
        
        # Calculate PnL
        exit_price = exit_order.avg_fill_price
        
        if position.side == 'BUY':
            # Long position
            gross_pnl = (exit_price - position.entry_price) * position.quantity
        else:
            # Short position
            gross_pnl = (position.entry_price - exit_price) * position.quantity
        
        # Subtract fees
        entry_fee = self.fee_calculator.calculate_fee(
            position.entry_price * position.quantity
        )
        exit_fee = self.fee_calculator.calculate_fee(
            exit_price * position.quantity
        )
        
        net_pnl = gross_pnl - entry_fee - exit_fee
        pnl_percent = (net_pnl / (position.entry_price * position.quantity)) * 100
        
        # Update position
        position.is_open = False
        position.exit_price = exit_price
        position.exit_order_id = exit_order.id
        position.pnl = net_pnl
        position.pnl_percent = pnl_percent
        position.closed_at = datetime.now()
        position.closure_reason = reason
        
        await self.position_manager.update_position(position)
        
        # Create trade record
        hold_duration = (position.closed_at - position.opened_at).total_seconds()
        
        trade = Trade(
            position_id=position.id,
            symbol=symbol,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            pnl=net_pnl,
            pnl_percent=pnl_percent,
            fees=entry_fee + exit_fee,
            hold_duration_seconds=int(hold_duration),
            strategy=position.strategy,
            closure_reason=reason,
            opened_at=position.opened_at,
            closed_at=position.closed_at
        )
        
        await self.db.save_trade(trade)
        
        # Log result
        logger.info(
            f"✅ Position {position.id} closed: "
            f"entry={position.entry_price:.2f}, exit={exit_price:.2f}, "
            f"PnL=${net_pnl:.2f} ({pnl_percent:+.2f}%), "
            f"hold={hold_duration/3600:.1f}h"
        )
        
        # Store PnL in order for return
        exit_order.pnl = net_pnl
        exit_order.pnl_percent = pnl_percent
        
        return exit_order
        
    except Exception as e:
        logger.error(f"Failed to close position {position.id}: {e}", exc_info=True)
        raise OrderExecutionError(f"Position closure failed: {e}")
```

---

## 📋 TEST SPECIFICATIONS

### File: `tests/unit/test_position_monitor.py`

```python
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from src.core.position_monitor import PositionMonitor
from src.models.position import Position


class TestPositionMonitor:
    """Unit tests for PositionMonitor"""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies"""
        return {
            'position_manager': Mock(),
            'order_manager': Mock(),
            'exchange': Mock(),
            'alert_manager': Mock(),
            'config': {
                'check_interval': 1,  # Fast for testing
                'trailing_stop_enabled': False,
                'max_position_age_hours': None,
                'adverse_spread_threshold': 0.005
            }
        }
    
    @pytest.fixture
    def monitor(self, mock_dependencies):
        """Create PositionMonitor instance"""
        return PositionMonitor(**mock_dependencies)
    
    def test_init(self, monitor):
        """Test initialization"""
        assert monitor.check_interval == 1
        assert monitor.running == False
        assert monitor.monitor_task is None
    
    @pytest.mark.asyncio
    async def test_start_stop(self, monitor):
        """Test starting and stopping monitor"""
        # Start
        await monitor.start()
        assert monitor.running == True
        assert monitor.monitor_task is not None
        
        # Stop
        await monitor.stop()
        assert monitor.running == False
    
    @pytest.mark.asyncio
    async def test_stop_loss_triggers_long_position(
        self,
        monitor,
        mock_dependencies
    ):
        """Test stop-loss triggers for long position"""
        # Create long position
        position = Position(
            id=1,
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42000.0,
            stop_loss=41160.0,  # 2% below entry
            take_profit=42840.0,
            quantity=0.1,
            is_open=True
        )
        
        # Mock current price below stop-loss
        mock_dependencies['exchange'].get_price = AsyncMock(return_value=41000.0)
        
        # Check stop-loss
        result = await monitor._check_stop_loss(position, 41000.0)
        
        assert result == True
    
    @pytest.mark.asyncio
    async def test_stop_loss_not_triggered(self, monitor):
        """Test stop-loss doesn't trigger when price above SL"""
        position = Position(
            id=1,
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42000.0,
            stop_loss=41160.0,
            quantity=0.1
        )
        
        # Price still above SL
        result = await monitor._check_stop_loss(position, 41500.0)
        
        assert result == False
    
    @pytest.mark.asyncio
    async def test_take_profit_triggers_long_position(self, monitor):
        """Test take-profit triggers for long position"""
        position = Position(
            id=1,
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42000.0,
            stop_loss=41160.0,
            take_profit=42840.0,  # 2% above entry
            quantity=0.1
        )
        
        # Price reached TP
        result = await monitor._check_take_profit(position, 42900.0)
        
        assert result == True
    
    @pytest.mark.asyncio
    async def test_trailing_stop_updates_long_position(self, monitor):
        """Test trailing stop updates as price moves up"""
        monitor.trailing_stop_enabled = True
        
        position = Position(
            id=1,
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42000.0,
            stop_loss=41160.0,  # 2% below
            trailing_stop_percent=0.02,
            quantity=0.1,
            max_price=None
        )
        
        # Price moved up
        await monitor._update_trailing_stop(position, 43000.0)
        
        # New SL should be 2% below new max
        expected_sl = 43000.0 * 0.98  # 42140.0
        
        assert position.stop_loss == pytest.approx(expected_sl, rel=0.01)
        assert position.max_price == 43000.0
    
    @pytest.mark.asyncio
    async def test_adverse_conditions_wide_spread(
        self,
        monitor,
        mock_dependencies
    ):
        """Test adverse conditions detected on wide spread"""
        position = Position(
            id=1,
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42000.0,
            quantity=0.1
        )
        
        # Mock order book with wide spread
        mock_dependencies['exchange'].get_order_book = AsyncMock(
            return_value={
                'bids': [[41900.0, 1.0]],  # Best bid
                'asks': [[42500.0, 1.0]]   # Best ask (1.4% spread!)
            }
        )
        
        result = await monitor._check_adverse_conditions(position, 42000.0)
        
        # Should detect wide spread (> 0.5% threshold)
        assert result == True
    
    @pytest.mark.asyncio
    async def test_close_position_with_reason_calls_order_manager(
        self,
        monitor,
        mock_dependencies
    ):
        """Test position closure calls order manager"""
        position = Position(
            id=1,
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42000.0,
            quantity=0.1
        )
        
        mock_dependencies['order_manager'].close_position = AsyncMock()
        mock_dependencies['alert_manager'].send_alert = AsyncMock()
        
        await monitor._close_position_with_reason(
            position,
            reason='STOP_LOSS_HIT',
            current_price=41000.0
        )
        
        # Verify order manager called
        mock_dependencies['order_manager'].close_position.assert_called_once()
        
        # Verify alert sent
        mock_dependencies['alert_manager'].send_alert.assert_called_once()
```

### File: `tests/unit/test_emergency_controller.py`

```python
import pytest
from unittest.mock import Mock, AsyncMock
import os

from src.core.emergency_controller import EmergencyController
from src.models.position import Position
from src.models.portfolio import Portfolio


class TestEmergencyController:
    """Unit tests for EmergencyController"""
    
    @pytest.fixture
    def mock_dependencies(self):
        return {
            'position_manager': Mock(),
            'order_manager': Mock(),
            'alert_manager': Mock(),
            'config': {
                'max_daily_loss_percent': 0.05,
                'max_single_position_loss_percent': 0.10,
                'kill_switch_file': '/tmp/TEST_KILL_SWITCH'
            }
        }
    
    @pytest.fixture
    def controller(self, mock_dependencies):
        return EmergencyController(**mock_dependencies)
    
    def test_init(self, controller):
        """Test initialization"""
        assert controller.emergency_mode == False
        assert controller.trading_paused == False
    
    @pytest.mark.asyncio
    async def test_emergency_triggered_on_daily_loss(
        self,
        controller,
        mock_dependencies
    ):
        """Test emergency triggers when daily loss exceeds threshold"""
        # Create portfolio with big loss
        portfolio = Mock()
        portfolio.get_daily_pnl_percent.return_value = -0.06  # -6% loss
        
        controller.trigger_emergency_stop = AsyncMock()
        
        # Check triggers
        result = await controller.check_emergency_triggers(portfolio)
        
        assert result == True
        controller.trigger_emergency_stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_no_emergency_on_small_loss(self, controller):
        """Test no emergency on small loss"""
        portfolio = Mock()
        portfolio.get_daily_pnl_percent.return_value = -0.02  # -2% (below threshold)
        
        result = await controller.check_emergency_triggers(portfolio)
        
        assert result == False
    
    @pytest.mark.asyncio
    async def test_kill_switch_file_triggers_emergency(
        self,
        controller,
        mock_dependencies
    ):
        """Test kill switch file triggers emergency"""
        # Create kill switch file
        kill_file = mock_dependencies['config']['kill_switch_file']
        
        # Create file
        with open(kill_file, 'w') as f:
            f.write('STOP')
        
        try:
            portfolio = Mock()
            portfolio.get_daily_pnl_percent.return_value = 0.0
            
            controller.trigger_emergency_stop = AsyncMock()
            
            result = await controller.check_emergency_triggers(portfolio)
            
            assert result == True
            controller.trigger_emergency_stop.assert_called_once()
        finally:
            # Cleanup
            if os.path.exists(kill_file):
                os.remove(kill_file)
    
    @pytest.mark.asyncio
    async def test_close_all_positions(self, controller, mock_dependencies):
        """Test closing all positions"""
        # Create mock positions
        positions = [
            Position(id=1, symbol='BTCUSDT', side='BUY', quantity=0.1, is_open=True),
            Position(id=2, symbol='ETHUSDT', side='BUY', quantity=1.0, is_open=True)
        ]
        
        mock_dependencies['position_manager'].get_open_positions = AsyncMock(
            return_value=positions
        )
        
        mock_dependencies['order_manager'].close_position = AsyncMock()
        
        # Close all
        result = await controller.close_all_positions(reason='TEST')
        
        # Verify
        assert result['positions_closed'] == 2
        assert len(result['failed_closures']) == 0
        
        # Verify close_position called for each
        assert mock_dependencies['order_manager'].close_position.call_count == 2
    
    @pytest.mark.asyncio
    async def test_pause_resume_trading(self, controller):
        """Test pause and resume trading"""
        # Pause
        await controller.pause_trading()
        assert controller.trading_paused == True
        
        # Resume
        await controller.resume_trading()
        assert controller.trading_paused == False
        assert controller.emergency_mode == False
```

### File: `tests/integration/test_monitoring_integration.py`

```python
import pytest
import asyncio
from datetime import datetime

from src.core.position_monitor import PositionMonitor
from src.core.emergency_controller import EmergencyController
from src.models.position import Position


@pytest.mark.integration
class TestMonitoringIntegration:
    """Integration tests for monitoring system"""
    
    @pytest.mark.asyncio
    async def test_full_position_lifecycle_with_monitoring(self):
        """
        Test complete position lifecycle with monitoring:
        1. Open position
        2. Start monitoring
        3. Simulate price movement to SL
        4. Verify position closed automatically
        """
        # This test requires actual exchange connection (testnet)
        # Implementation depends on test environment setup
        pass
    
    @pytest.mark.asyncio
    async def test_emergency_stop_during_monitoring(self):
        """
        Test emergency stop while monitoring active:
        1. Open multiple positions
        2. Start monitoring
        3. Trigger emergency stop
        4. Verify all positions closed
        5. Verify trading paused
        """
        pass
    
    @pytest.mark.asyncio
    async def test_position_monitor_handles_websocket_disconnect(self):
        """
        Test position monitor handles WebSocket disconnect:
        1. Start monitoring
        2. Simulate WebSocket disconnect
        3. Verify monitoring continues with REST API fallback
        4. Verify positions still monitored correctly
        """
        pass
```

---

## 🚀 CURSOR PROMPTS

Copy-paste these prompts to Cursor:

### Prompt 1: Create Position Monitor

```
I need you to create src/core/position_monitor.py implementing the PositionMonitor class.

Read the specification in WEEK1_DAY1-2_SPEC.md (Position Monitor section).

Requirements:
1. Implement all methods as specified
2. Use async/await throughout
3. Add comprehensive error handling
4. Add detailed logging at every step
5. Include type hints for all functions
6. Add docstrings with Args/Returns/Raises
7. Handle edge cases (no positions, API errors, etc)

Critical methods:
- _monitor_loop(): Main monitoring loop (runs every 5 seconds)
- _check_position(): Check single position for exit conditions
- _check_stop_loss(): Detect SL breach
- _check_take_profit(): Detect TP breach
- _update_trailing_stop(): Update trailing SL
- _close_position_with_reason(): Close position and log

Make this production-ready code - no placeholders, no TODOs.
```

### Prompt 2: Create Emergency Controller

```
Create src/core/emergency_controller.py implementing the EmergencyController class.

Read the specification in WEEK1_DAY1-2_SPEC.md (Emergency Controller section).

Requirements:
1. Implement emergency triggers (daily loss, kill switch file)
2. Implement close_all_positions() with concurrent execution
3. Implement pause/resume trading
4. Add comprehensive error handling
5. Send critical alerts via alert_manager
6. Log all emergency actions

Critical methods:
- check_emergency_triggers(): Check if emergency conditions met
- trigger_emergency_stop(): Execute emergency stop sequence
- close_all_positions(): Close all positions concurrently
- pause_trading() / resume_trading(): Control trading state

This is a safety-critical component - code must be bulletproof.
```

### Prompt 3: Enhance Order Manager

```
Modify src/core/order_manager.py to add the close_position() method.

Read the specification in WEEK1_DAY1-2_SPEC.md (Order Manager Enhancement section).

The method must:
1. Accept position, reason, emergency flag, optional current price
2. Create opposite side market order
3. Execute order on exchange
4. Wait for fill (with timeout)
5. Calculate PnL (including fees)
6. Update position in database
7. Create trade record
8. Return exit order with PnL

Error handling:
- Handle order rejection
- Handle partial fills
- Handle timeout
- Raise OrderExecutionError on failure

This method will be called by PositionMonitor - must be reliable.
```

### Prompt 4: Create Unit Tests

```
Create comprehensive unit tests:

1. tests/unit/test_position_monitor.py
   - Test SL/TP detection logic
   - Test trailing stop updates
   - Test adverse conditions detection
   - Mock all external dependencies

2. tests/unit/test_emergency_controller.py
   - Test emergency trigger detection
   - Test close_all_positions()
   - Test kill switch file detection
   - Test pause/resume

Use pytest and pytest-asyncio.
Follow the test specifications in WEEK1_DAY1-2_SPEC.md.
Aim for 90%+ coverage of critical logic.
```

---

## ✅ ACCEPTANCE CRITERIA

Day 1-2 is complete when:

```
Code:
□ PositionMonitor class created (300+ lines)
□ EmergencyController class created (200+ lines)
□ close_position() method added to OrderManager
□ All methods have type hints
□ All methods have docstrings
□ Comprehensive error handling everywhere
□ Detailed logging at every step

Tests:
□ test_position_monitor.py created (10+ tests)
□ test_emergency_controller.py created (8+ tests)
□ All unit tests passing
□ 90%+ coverage of critical logic

Integration:
□ Can import all new modules without errors
□ Position monitor starts/stops cleanly
□ Emergency controller initializes correctly
□ No syntax errors or import issues

Validation:
□ Run: python -m pytest tests/unit/test_position_monitor.py -v
□ Run: python -m pytest tests/unit/test_emergency_controller.py -v
□ All tests GREEN
```

---

## 📊 ESTIMATED TIME

- Position Monitor: 4-6 hours (with Cursor assistance)
- Emergency Controller: 2-3 hours
- Order Manager Enhancement: 2-3 hours
- Unit Tests: 3-4 hours
- Integration & Testing: 2-3 hours

**Total: 13-19 hours (1.5-2 days)**

---

**READY TO START! 🚀**

Give these prompts to Cursor one by one and watch it build production-ready code!