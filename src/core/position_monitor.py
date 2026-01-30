"""
Position Monitor - Real-time SL/TP monitoring.

Continuously monitors all open positions and triggers stop-loss/take-profit
when price reaches threshold. This is a CRITICAL safety component.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.core.exchange import BinanceExchange
from src.core.logger import get_logger
from src.data.database import TimescaleDBClient
from src.data.market_data import MarketDataManager
from src.execution.lifecycle import OrderLifecycleManager
from src.risk.manager import RiskManager

logger = get_logger(__name__)


class PositionMonitor:
    """
    Real-time position monitoring with automatic SL/TP execution.
    
    Continuously monitors all open positions and automatically closes them
    when stop-loss or take-profit thresholds are hit.
    
    Features:
    - Stop-loss monitoring (every 5 seconds)
    - Take-profit monitoring
    - Trailing stop support
    - Position age limits
    - Adverse market condition detection
    - Automatic position closure
    """
    
    def __init__(
        self,
        risk_manager: RiskManager,
        exchange: BinanceExchange,
        order_lifecycle: OrderLifecycleManager,
        database: Optional[TimescaleDBClient] = None,
        market_data: Optional[MarketDataManager] = None,
        check_interval: float = 5.0,
        trailing_stop_enabled: bool = False,
        max_position_age_hours: Optional[float] = None,
        adverse_spread_threshold: float = 0.005
    ):
        """
        Initialize position monitor.

        Args:
            risk_manager: RiskManager instance with open positions
            exchange: Exchange instance for price data and order execution
            order_lifecycle: OrderLifecycleManager for order tracking
            database: Optional TimescaleDBClient for trade logging
            market_data: Optional MarketDataManager for order book data
            check_interval: Seconds between position checks (default: 5.0)
            trailing_stop_enabled: Enable trailing stops (default: False)
            max_position_age_hours: Max hold time in hours (default: None = no limit)
            adverse_spread_threshold: Close if spread > threshold (default: 0.5%)

        Raises:
            ValueError: If check_interval <= 0
        """
        if check_interval <= 0:
            raise ValueError(f"check_interval must be > 0, got {check_interval}")

        self.risk_manager = risk_manager
        self.exchange = exchange
        self.order_lifecycle = order_lifecycle
        self.database = database
        self.market_data = market_data

        self.check_interval = check_interval
        self.trailing_stop_enabled = trailing_stop_enabled
        self.max_position_age_hours = max_position_age_hours
        self.adverse_spread_threshold = adverse_spread_threshold

        self.running = False
        self.monitor_task: Optional[asyncio.Task] = None

        logger.info(
            f"PositionMonitor initialized: "
            f"check_interval={self.check_interval}s, "
            f"trailing_stop={trailing_stop_enabled}, "
            f"max_age={max_position_age_hours}h, "
            f"database={'enabled' if database else 'disabled'}"
        )
    
    async def start(self) -> None:
        """
        Start position monitoring loop.
        
        Creates asyncio task that runs _monitor_loop() continuously.
        Can be called multiple times safely (will not start if already running).
        """
        if self.running:
            logger.warning("Position monitor already running")
            return
        
        self.running = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Position monitor started")
    
    async def stop(self) -> None:
        """
        Stop position monitoring loop.
        
        Cancels monitoring task gracefully and waits for it to finish.
        Can be called multiple times safely.
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
            finally:
                self.monitor_task = None
        
        logger.info("Position monitor stopped")
    
    async def _monitor_loop(self) -> None:
        """
        Main monitoring loop - runs continuously.
        
        Logic:
        1. Get all open positions from RiskManager
        2. For each position:
            a. Get current price
            b. Check stop-loss
            c. Check take-profit
            d. Update trailing stop (if enabled)
            e. Check adverse conditions
            f. Check age limit
        3. Sleep for check_interval seconds
        4. Repeat
        
        Error Handling:
        - Individual position errors logged but don't stop loop
        - Critical errors logged and loop continues with retry
        - Cancellation handled gracefully
        """
        logger.info("Position monitoring loop started")
        
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while self.running:
            try:
                # Get all open positions
                positions = self.risk_manager.open_positions
                
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
                                f"Error monitoring position {position.get('id', 'unknown')}: {e}",
                                exc_info=True
                            )
                            # Continue with other positions
                    
                    # Reset error counter on successful iteration
                    consecutive_errors = 0
                
                # Sleep before next check
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                logger.info("Monitoring loop cancelled")
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error(
                    f"Critical error in monitoring loop (error #{consecutive_errors}): {e}",
                    exc_info=True
                )
                
                # If too many consecutive errors, stop monitoring
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(
                        f"Too many consecutive errors ({consecutive_errors}), "
                        f"stopping position monitor"
                    )
                    self.running = False
                    break
                
                # Sleep and retry
                await asyncio.sleep(self.check_interval)
        
        logger.info("Position monitoring loop ended")
    
    async def _check_position(self, position: Dict) -> None:
        """
        Check single position for exit conditions.
        
        Exit conditions checked (in order):
        1. Stop-loss hit
        2. Take-profit hit
        3. Trailing stop hit (if enabled)
        4. Max age exceeded
        5. Adverse market conditions
        
        Args:
            position: Position dictionary from RiskManager.open_positions
        """
        position_id = position.get('id', 'unknown')
        symbol = position.get('symbol', 'UNKNOWN')
        
        # Validate position data
        if not symbol or symbol == 'UNKNOWN':
            logger.warning(f"Invalid position {position_id}: missing symbol")
            return
        
        # Get current price
        try:
            current_price = await self.exchange.get_ticker_price(f"{symbol}")
            if current_price is None:
                logger.warning(f"Could not get price for {symbol}, skipping check")
                return
        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
            return
        
        entry_price = position.get('entry_price', 0.0)
        stop_loss = position.get('stop_loss')
        take_profit = position.get('take_profit')
        side = position.get('side', 'BUY')
        
        sl_str = f"{stop_loss:.2f}" if stop_loss is not None else "None"
        tp_str = f"{take_profit:.2f}" if take_profit is not None else "None"
        logger.debug(
            f"Checking position {position_id}: {symbol} {side} "
            f"current={current_price:.2f} entry={entry_price:.2f} "
            f"SL={sl_str} TP={tp_str}"
        )
        
        # 1. Check Stop-Loss
        if stop_loss is not None:
            if await self._check_stop_loss(position, current_price):
                await self._close_position_with_reason(
                    position,
                    reason="STOP_LOSS_HIT",
                    current_price=current_price
                )
                return
        
        # 2. Check Take-Profit
        if take_profit is not None:
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
        if self.max_position_age_hours is not None:
            opened_at = position.get('opened_at')
            if opened_at:
                if isinstance(opened_at, str):
                    # Parse datetime string if needed
                    try:
                        opened_at = datetime.fromisoformat(opened_at.replace('Z', '+00:00'))
                    except Exception:
                        logger.warning(f"Could not parse opened_at for position {position_id}")
                        opened_at = None
                
                if opened_at and isinstance(opened_at, datetime):
                    age_hours = (datetime.now() - opened_at.replace(tzinfo=None)).total_seconds() / 3600
                    if age_hours > self.max_position_age_hours:
                        logger.info(
                            f"Position {position_id} exceeded max age "
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
    
    async def _check_stop_loss(
        self,
        position: Dict,
        current_price: float
    ) -> bool:
        """
        Check if stop-loss should trigger.
        
        Logic:
        - LONG position (BUY): current_price <= stop_loss
        - SHORT position (SELL): current_price >= stop_loss
        
        Args:
            position: Position dictionary
            current_price: Current market price
            
        Returns:
            True if stop-loss hit, False otherwise
        """
        stop_loss = position.get('stop_loss')
        if stop_loss is None:
            return False
        
        side = position.get('side', 'BUY')
        symbol = position.get('symbol', 'UNKNOWN')
        
        if side == 'BUY':
            # Long position: price dropped to or below SL
            if current_price <= stop_loss:
                logger.warning(
                    f"⚠️ STOP-LOSS HIT: {symbol} "
                    f"price {current_price:.2f} <= SL {stop_loss:.2f} "
                    f"(loss: {((current_price - position.get('entry_price', 0)) / position.get('entry_price', 1) * 100):.2f}%)"
                )
                return True
        
        elif side == 'SELL':
            # Short position: price rose to or above SL
            if current_price >= stop_loss:
                logger.warning(
                    f"⚠️ STOP-LOSS HIT: {symbol} "
                    f"price {current_price:.2f} >= SL {stop_loss:.2f} "
                    f"(loss: {((position.get('entry_price', 0) - current_price) / position.get('entry_price', 1) * 100):.2f}%)"
                )
                return True
        
        return False
    
    async def _check_take_profit(
        self,
        position: Dict,
        current_price: float
    ) -> bool:
        """
        Check if take-profit should trigger.
        
        Logic:
        - LONG position (BUY): current_price >= take_profit
        - SHORT position (SELL): current_price <= take_profit
        
        Args:
            position: Position dictionary
            current_price: Current market price
            
        Returns:
            True if take-profit hit, False otherwise
        """
        take_profit = position.get('take_profit')
        if take_profit is None:
            return False
        
        side = position.get('side', 'BUY')
        symbol = position.get('symbol', 'UNKNOWN')
        
        if side == 'BUY':
            # Long position: price rose to or above TP
            if current_price >= take_profit:
                logger.info(
                    f"✅ TAKE-PROFIT HIT: {symbol} "
                    f"price {current_price:.2f} >= TP {take_profit:.2f} "
                    f"(profit: {((current_price - position.get('entry_price', 0)) / position.get('entry_price', 1) * 100):.2f}%)"
                )
                return True
        
        elif side == 'SELL':
            # Short position: price dropped to or below TP
            if current_price <= take_profit:
                logger.info(
                    f"✅ TAKE-PROFIT HIT: {symbol} "
                    f"price {current_price:.2f} <= TP {take_profit:.2f} "
                    f"(profit: {((position.get('entry_price', 0) - current_price) / position.get('entry_price', 1) * 100):.2f}%)"
                )
                return True
        
        return False
    
    async def _update_trailing_stop(
        self,
        position: Dict,
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
            position: Position dictionary
            current_price: Current market price
        """
        trailing_stop_percent = position.get('trailing_stop_percent')
        if trailing_stop_percent is None:
            return
        
        side = position.get('side', 'BUY')
        symbol = position.get('symbol', 'UNKNOWN')
        stop_loss = position.get('stop_loss')
        
        if stop_loss is None:
            return
        
        if side == 'BUY':
            # Long position: track max price
            max_price = position.get('max_price')
            
            if max_price is None or current_price > max_price:
                position['max_price'] = current_price
                max_price = current_price
                
                # Calculate new stop-loss
                new_stop = max_price * (1 - trailing_stop_percent)
                
                # Only update if new stop is higher than current
                if new_stop > stop_loss:
                    old_stop = stop_loss
                    position['stop_loss'] = new_stop
                    
                    logger.info(
                        f"📈 Trailing stop updated: {symbol} "
                        f"SL {old_stop:.2f} → {new_stop:.2f} "
                        f"(max_price={max_price:.2f})"
                    )
        
        elif side == 'SELL':
            # Short position: track min price
            min_price = position.get('min_price')
            
            if min_price is None or current_price < min_price:
                position['min_price'] = current_price
                min_price = current_price
                
                # Calculate new stop-loss
                new_stop = min_price * (1 + trailing_stop_percent)
                
                # Only update if new stop is lower than current
                if new_stop < stop_loss:
                    old_stop = stop_loss
                    position['stop_loss'] = new_stop
                    
                    logger.info(
                        f"📉 Trailing stop updated: {symbol} "
                        f"SL {old_stop:.2f} → {new_stop:.2f} "
                        f"(min_price={min_price:.2f})"
                    )
    
    async def _check_adverse_conditions(
        self,
        position: Dict,
        current_price: float
    ) -> bool:
        """
        Check for adverse market conditions that warrant closing position.
        
        Conditions checked:
        1. Spread widened significantly (> threshold)
        2. Liquidity dried up (order book depth too low)
        
        Args:
            position: Position dictionary
            current_price: Current market price
            
        Returns:
            True if adverse conditions detected, False otherwise
        """
        symbol = position.get('symbol', 'UNKNOWN')
        
        try:
            # Get current order book
            if self.market_data:
                ob_data = await self.market_data.get_order_book_snapshot(symbol, limit=20)
            else:
                # Fallback: use exchange directly
                from src.analysis.orderbook import OrderBook
                from src.data.normalization import normalize_orderbook_data
                
                # Get order book from exchange
                ob_raw = await self.exchange.get_order_book(symbol, limit=20)
                ob_data = normalize_orderbook_data(ob_raw, symbol)
            
            if not ob_data or 'bids' not in ob_data or 'asks' not in ob_data:
                logger.warning(f"Invalid order book data for {symbol}")
                return False
            
            bids = ob_data.get('bids', [])
            asks = ob_data.get('asks', [])
            
            if not bids or not asks:
                logger.warning(f"Empty order book for {symbol}")
                return False
            
            # Check spread
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
            spread_percent = (best_ask - best_bid) / best_bid if best_bid > 0 else 0.0
            
            if spread_percent > self.adverse_spread_threshold:
                logger.warning(
                    f"⚠️ Wide spread detected: {symbol} "
                    f"spread={spread_percent*100:.2f}% > threshold={self.adverse_spread_threshold*100:.2f}%"
                )
                return True
            
            # Check liquidity (top 10 levels)
            bid_liquidity = sum([float(b[1]) for b in bids[:10]])
            ask_liquidity = sum([float(a[1]) for a in asks[:10]])
            total_liquidity_usdt = (bid_liquidity + ask_liquidity) * current_price / 2
            
            if total_liquidity_usdt < 10000:  # Less than $10k liquidity
                logger.warning(
                    f"⚠️ Low liquidity detected: {symbol} "
                    f"liquidity={total_liquidity_usdt:.0f} USDT"
                )
                return True
        
        except Exception as e:
            logger.error(f"Error checking adverse conditions for {symbol}: {e}")
            # Don't close on error - better to keep position than close incorrectly
            return False
        
        return False
    
    async def _close_position_with_reason(
        self,
        position: Dict,
        reason: str,
        current_price: float
    ) -> None:
        """
        Close position and log reason.
        
        This method calls the exchange to close the position via market order.
        
        Args:
            position: Position dictionary to close
            reason: Closure reason (STOP_LOSS_HIT, TAKE_PROFIT_HIT, etc)
            current_price: Price at closure (for logging)
        """
        position_id = position.get('id', 'unknown')
        symbol = position.get('symbol', 'UNKNOWN')
        side = position.get('side', 'BUY')
        quantity = position.get('quantity', 0.0)
        
        logger.info(
            f"Closing position {position_id} ({symbol} {side}): {reason} "
            f"@ {current_price:.2f}"
        )
        
        try:
            # Determine exit side (opposite of entry)
            exit_side = 'SELL' if side == 'BUY' else 'BUY'
            
            # Create market order to close position
            logger.debug(
                f"Creating market order to close: {exit_side} {quantity} {symbol}"
            )
            
            # Place market order via exchange
            order_response = await self.exchange.place_order(
                symbol=symbol,
                side=exit_side,
                order_type='MARKET',
                quantity=quantity
            )
            
            logger.info(
                f"✅ Position closure order placed: {symbol} {exit_side} "
                f"order_id={order_response.get('orderId')}"
            )
            
            # Wait a moment for order to fill
            await asyncio.sleep(2)
            
            # Check order status
            order_id = order_response.get('orderId')
            if isinstance(order_id, str):
                order_id = int(order_id)
            
            order_status = await self.exchange.get_order_status(
                symbol,
                order_id
            )
            
            if order_status.get('status') == 'FILLED':
                filled_qty = float(order_status.get('executedQty', quantity))
                fill_price = float(order_status.get('price', current_price))

                # Calculate PnL
                entry_price = position.get('entry_price', 0.0)
                if side == 'BUY':
                    gross_pnl = (fill_price - entry_price) * filled_qty
                else:
                    gross_pnl = (entry_price - fill_price) * filled_qty

                # Calculate fees (0.1% maker/taker)
                entry_fee = entry_price * quantity * 0.001
                exit_fee = fill_price * filled_qty * 0.001
                total_fees = entry_fee + exit_fee
                net_pnl = gross_pnl - total_fees
                pnl_percent = (net_pnl / (entry_price * quantity)) * 100 if entry_price > 0 else 0.0

                # Calculate hold duration
                entry_time = position.get('opened_at')
                exit_time = datetime.now()
                if entry_time:
                    hold_duration = int((exit_time - entry_time).total_seconds())
                else:
                    hold_duration = 0

                logger.info(
                    f"✅ Position {position_id} closed: "
                    f"entry={entry_price:.2f}, exit={fill_price:.2f}, "
                    f"PnL=${net_pnl:.2f} ({pnl_percent:+.2f}%), "
                    f"fees=${total_fees:.2f}, reason={reason}"
                )

                # Store trade in database
                if self.database and self.database.is_connected():
                    trade_record = {
                        'id': position_id,
                        'symbol': symbol,
                        'side': side,
                        'entry_price': entry_price,
                        'exit_price': fill_price,
                        'quantity': filled_qty,
                        'position_value_usdt': entry_price * quantity,
                        'stop_loss': position.get('stop_loss'),
                        'take_profit': position.get('take_profit'),
                        'trailing_stop': position.get('trailing_stop_percent') is not None,
                        'pnl': net_pnl,
                        'pnl_percent': pnl_percent,
                        'entry_fee': entry_fee,
                        'exit_fee': exit_fee,
                        'total_fees': total_fees,
                        'closure_reason': reason,
                        'strategy_name': position.get('strategy_name', 'InstitutionalStrategy'),
                        'entry_time': entry_time or exit_time,
                        'exit_time': exit_time,
                        'hold_duration_seconds': hold_duration
                    }

                    try:
                        await self.database.store_completed_trade(trade_record)
                    except Exception as db_error:
                        logger.error(f"Failed to store trade in database: {db_error}")

                # Remove position from RiskManager
                self.risk_manager.remove_position(position_id)
                
            else:
                logger.warning(
                    f"Position closure order not filled: {symbol} "
                    f"status={order_status.get('status')}"
                )
                # Order might be pending - will be checked in next iteration
        
        except Exception as e:
            logger.error(
                f"Failed to close position {position_id} ({symbol}): {e}",
                exc_info=True
            )
            # Don't remove position if closure failed - will retry next iteration
