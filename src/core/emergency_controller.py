"""
Emergency Controller - Safety-critical emergency controls.

Provides emergency controls for crisis situations including kill switch,
emergency position closure, and trading pause/resume functionality.
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.exchange import BinanceExchange
from src.core.logger import get_logger
from src.risk.manager import RiskManager

logger = get_logger(__name__)


class EmergencyController:
    """
    Emergency controls for crisis situations.
    
    Provides safety-critical emergency controls including:
    - Kill switch (file-based)
    - Daily loss limit triggers
    - Single position loss triggers
    - Emergency position closure
    - Trading pause/resume
    
    This is a CRITICAL safety component - must be bulletproof.
    """
    
    def __init__(
        self,
        risk_manager: RiskManager,
        exchange: BinanceExchange,
        max_daily_loss_percent: float = 0.05,
        max_single_position_loss_percent: float = 0.10,
        kill_switch_file: Optional[str] = None
    ):
        """
        Initialize emergency controller.
        
        Args:
            risk_manager: RiskManager instance with portfolio state
            exchange: Exchange instance for price data and order execution
            max_daily_loss_percent: Trigger emergency at daily loss (default: 5%)
            max_single_position_loss_percent: Trigger on big position loss (default: 10%)
            kill_switch_file: File path to check for kill switch (default: platform-specific)
            
        Raises:
            ValueError: If loss percentages are invalid
        """
        if max_daily_loss_percent <= 0 or max_daily_loss_percent > 1.0:
            raise ValueError(
                f"max_daily_loss_percent must be between 0 and 1.0, got {max_daily_loss_percent}"
            )
        if max_single_position_loss_percent <= 0 or max_single_position_loss_percent > 1.0:
            raise ValueError(
                f"max_single_position_loss_percent must be between 0 and 1.0, "
                f"got {max_single_position_loss_percent}"
            )
        
        self.risk_manager = risk_manager
        self.exchange = exchange
        
        self.max_daily_loss_percent = max_daily_loss_percent
        self.max_single_position_loss_percent = max_single_position_loss_percent
        
        # Set default kill switch file path (platform-specific)
        if kill_switch_file is None:
            if os.name == 'nt':  # Windows
                kill_switch_file = os.path.join(os.getenv('TEMP', 'C:\\temp'), 'KILL_SWITCH')
            else:  # Unix/Linux/Mac
                kill_switch_file = '/tmp/KILL_SWITCH'
        
        self.kill_switch_file = Path(kill_switch_file)
        
        self.emergency_mode = False
        self.trading_paused = False
        
        logger.info(
            f"EmergencyController initialized: "
            f"max_daily_loss={max_daily_loss_percent*100:.1f}%, "
            f"max_single_loss={max_single_position_loss_percent*100:.1f}%, "
            f"kill_switch={self.kill_switch_file}"
        )
    
    async def check_emergency_triggers(
        self,
        current_balance: Optional[float] = None
    ) -> bool:
        """
        Check if emergency conditions met.
        
        Triggers checked (in order):
        1. Daily loss exceeds threshold
        2. Single position loss exceeds threshold
        3. Kill switch file exists
        
        Args:
            current_balance: Optional current account balance (if None, uses RiskManager's daily_pnl)
            
        Returns:
            True if emergency triggered, False otherwise
        """
        # Check daily loss
        if current_balance is not None:
            self.risk_manager.update_daily_pnl(current_balance)
        
        daily_pnl = self.risk_manager.daily_pnl
        daily_start_balance = self.risk_manager.daily_start_balance
        
        if daily_start_balance > 0:
            daily_pnl_percent = (daily_pnl / daily_start_balance)
            
            if daily_pnl_percent <= -self.max_daily_loss_percent:
                logger.critical(
                    f"🚨 EMERGENCY: Daily loss {daily_pnl_percent*100:.2f}% exceeds "
                    f"threshold -{self.max_daily_loss_percent*100:.2f}% "
                    f"(PnL: ${daily_pnl:.2f}, Start: ${daily_start_balance:.2f})"
                )
                await self.trigger_emergency_stop(
                    reason=f"Daily loss {daily_pnl_percent*100:.2f}%"
                )
                return True
        
        # Check single position loss
        positions = self.risk_manager.open_positions
        
        for position in positions:
            try:
                symbol = position.get('symbol', 'UNKNOWN')
                if symbol == 'UNKNOWN':
                    continue
                
                # Get current price
                current_price = await self.exchange.get_ticker_price(f"{symbol}")
                if current_price is None:
                    logger.warning(f"Could not get price for {symbol}, skipping position loss check")
                    continue
                
                # Calculate PnL percent
                entry_price = position.get('entry_price', 0.0)
                quantity = position.get('quantity', 0.0)
                side = position.get('side', 'BUY')
                
                if entry_price <= 0 or quantity <= 0:
                    continue
                
                # Calculate unrealized PnL
                if side == 'BUY':
                    unrealized_pnl = (current_price - entry_price) * quantity
                else:  # SELL
                    unrealized_pnl = (entry_price - current_price) * quantity
                
                position_value = entry_price * quantity
                pnl_percent = (unrealized_pnl / position_value) if position_value > 0 else 0.0
                
                if pnl_percent <= -self.max_single_position_loss_percent:
                    logger.critical(
                        f"🚨 EMERGENCY: Position {symbol} loss {pnl_percent*100:.2f}% "
                        f"exceeds threshold -{self.max_single_position_loss_percent*100:.2f}% "
                        f"(PnL: ${unrealized_pnl:.2f}, Entry: ${entry_price:.2f}, Current: ${current_price:.2f})"
                    )
                    await self.trigger_emergency_stop(
                        reason=f"Position {symbol} loss {pnl_percent*100:.2f}%"
                    )
                    return True
            
            except Exception as e:
                logger.error(
                    f"Error checking position loss for {position.get('symbol', 'unknown')}: {e}",
                    exc_info=True
                )
                # Continue with other positions
                continue
        
        # Check kill switch file
        try:
            if self.kill_switch_file.exists():
                logger.critical(
                    f"🚨 EMERGENCY: Kill switch file detected at {self.kill_switch_file}"
                )
                await self.trigger_emergency_stop(reason="Kill switch file detected")
                return True
        except Exception as e:
            logger.error(f"Error checking kill switch file: {e}")
            # Don't trigger emergency on file check error
        
        return False
    
    async def trigger_emergency_stop(self, reason: str) -> None:
        """
        Trigger emergency stop - close all positions immediately.
        
        Actions:
        1. Set emergency mode flag
        2. Log critical alert
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
        
        logger.critical(
            f"🚨🚨🚨 EMERGENCY STOP TRIGGERED: {reason} 🚨🚨🚨"
        )
        logger.critical(
            f"Emergency stop timestamp: {datetime.now().isoformat()}"
        )
        
        # Close all positions
        try:
            result = await self.close_all_positions(reason=f"EMERGENCY: {reason}")
            
            logger.critical(
                f"Emergency position closure complete: "
                f"{result['positions_closed']} positions closed, "
                f"{len(result['failed_closures'])} failed, "
                f"Total PnL: ${result['total_pnl']:.2f}"
            )
            
            if result['failed_closures']:
                logger.critical(
                    f"⚠️ WARNING: {len(result['failed_closures'])} positions failed to close: "
                    f"{[f['symbol'] for f in result['failed_closures']]}"
                )
        
        except Exception as e:
            logger.error(
                f"Error closing positions during emergency: {e}",
                exc_info=True
            )
            # Continue even if closure fails - trading must be paused
        
        # Pause trading
        self.trading_paused = True
        
        logger.critical("Emergency stop completed - Trading PAUSED")
    
    async def close_all_positions(self, reason: str = "MANUAL") -> Dict[str, Any]:
        """
        Close all open positions immediately.
        
        Uses market orders for immediate execution. Positions are closed
        concurrently for speed.
        
        Args:
            reason: Closure reason
            
        Returns:
            Dictionary with:
            - positions_closed: Number of positions successfully closed
            - failed_closures: List of positions that failed to close
            - total_pnl: Total PnL from closures (estimated)
        """
        positions = self.risk_manager.open_positions
        
        if not positions:
            logger.info("No open positions to close")
            return {
                'positions_closed': 0,
                'failed_closures': [],
                'total_pnl': 0.0
            }
        
        logger.warning(
            f"Closing {len(positions)} positions (reason: {reason})"
        )
        
        # Close positions concurrently
        tasks = []
        for position in positions:
            task = self._close_single_position(position, reason)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        closed_count = 0
        failed = []
        total_pnl = 0.0
        
        for position, result in zip(positions, results):
            position_id = position.get('id', 'unknown')
            symbol = position.get('symbol', 'UNKNOWN')
            
            if isinstance(result, Exception):
                logger.error(
                    f"Failed to close position {position_id} ({symbol}): {result}"
                )
                failed.append({
                    'position_id': position_id,
                    'symbol': symbol,
                    'error': str(result)
                })
            elif result is None:
                # Position closure failed silently
                failed.append({
                    'position_id': position_id,
                    'symbol': symbol,
                    'error': 'Closure failed silently'
                })
            else:
                closed_count += 1
                pnl = result.get('pnl', 0.0)
                total_pnl += pnl
                
                logger.info(
                    f"✅ Closed position {position_id} ({symbol}): "
                    f"PnL=${pnl:.2f}"
                )
        
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
    
    async def _close_single_position(
        self,
        position: Dict,
        reason: str
    ) -> Optional[Dict[str, float]]:
        """
        Close a single position.
        
        Args:
            position: Position dictionary
            reason: Closure reason
            
        Returns:
            Dictionary with 'pnl' key, or None if failed
        """
        position_id = position.get('id', 'unknown')
        symbol = position.get('symbol', 'UNKNOWN')
        side = position.get('side', 'BUY')
        quantity = position.get('quantity', 0.0)
        entry_price = position.get('entry_price', 0.0)
        
        if symbol == 'UNKNOWN' or quantity <= 0:
            logger.warning(f"Invalid position {position_id}, skipping")
            return None
        
        try:
            # Get current price
            current_price = await self.exchange.get_ticker_price(f"{symbol}")
            if current_price is None:
                logger.warning(f"Could not get price for {symbol}, skipping closure")
                return None
            
            # Determine exit side (opposite of entry)
            exit_side = 'SELL' if side == 'BUY' else 'BUY'
            
            logger.debug(
                f"Closing position {position_id}: {symbol} {exit_side} {quantity} @ market"
            )
            
            # Place market order to close position
            order_response = await self.exchange.place_order(
                symbol=symbol,
                side=exit_side,
                order_type='MARKET',
                quantity=quantity
            )
            
            order_id = order_response.get('orderId')
            logger.info(
                f"Position closure order placed: {symbol} {exit_side} "
                f"order_id={order_id}"
            )
            
            # Wait for order to fill
            await asyncio.sleep(2)
            
            # Check order status
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
                if side == 'BUY':
                    gross_pnl = (fill_price - entry_price) * filled_qty
                else:
                    gross_pnl = (entry_price - fill_price) * filled_qty
                
                # Estimate fees (0.1% maker/taker)
                entry_fee = entry_price * quantity * 0.001
                exit_fee = fill_price * filled_qty * 0.001
                net_pnl = gross_pnl - entry_fee - exit_fee
                
                # Remove position from RiskManager
                self.risk_manager.remove_position(position_id)
                
                return {'pnl': net_pnl}
            else:
                logger.warning(
                    f"Position closure order not filled: {symbol} "
                    f"status={order_status.get('status')}"
                )
                return None
        
        except Exception as e:
            logger.error(
                f"Failed to close position {position_id} ({symbol}): {e}",
                exc_info=True
            )
            return None
    
    async def pause_trading(self) -> None:
        """
        Pause new position opening (keep existing positions).
        
        Sets trading_paused flag to True. Existing positions remain open
        and continue to be monitored.
        """
        if self.trading_paused:
            logger.warning("Trading already paused")
            return
        
        self.trading_paused = True
        logger.warning("🟡 Trading paused - no new positions will be opened")
        logger.warning(
            f"Trading pause timestamp: {datetime.now().isoformat()}"
        )
    
    async def resume_trading(self) -> None:
        """
        Resume trading after pause.
        
        Sets trading_paused flag to False and clears emergency_mode flag.
        Trading can resume normally.
        """
        if not self.trading_paused:
            logger.info("Trading already active")
            return
        
        self.trading_paused = False
        self.emergency_mode = False
        
        logger.info("🟢 Trading resumed")
        logger.info(
            f"Trading resume timestamp: {datetime.now().isoformat()}"
        )
    
    def is_trading_paused(self) -> bool:
        """
        Check if trading is paused.
        
        Returns:
            True if trading is paused, False otherwise
        """
        return self.trading_paused
    
    def is_emergency_mode(self) -> bool:
        """
        Check if emergency mode is active.
        
        Returns:
            True if emergency mode is active, False otherwise
        """
        return self.emergency_mode
    
    def create_kill_switch_file(self) -> None:
        """
        Create kill switch file to trigger emergency stop.
        
        This is a convenience method for manual emergency stop.
        The file will be checked by check_emergency_triggers().
        """
        try:
            # Ensure parent directory exists
            self.kill_switch_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Create file
            with open(self.kill_switch_file, 'w') as f:
                f.write(f"KILL_SWITCH\nCreated: {datetime.now().isoformat()}\n")
            
            logger.critical(
                f"🚨 Kill switch file created at {self.kill_switch_file}"
            )
            logger.critical(
                "Emergency stop will be triggered on next check_emergency_triggers() call"
            )
        
        except Exception as e:
            logger.error(f"Failed to create kill switch file: {e}", exc_info=True)
            raise
    
    def remove_kill_switch_file(self) -> None:
        """
        Remove kill switch file.
        
        This clears the kill switch if it exists.
        """
        try:
            if self.kill_switch_file.exists():
                self.kill_switch_file.unlink()
                logger.info(f"Kill switch file removed: {self.kill_switch_file}")
        except Exception as e:
            logger.error(f"Failed to remove kill switch file: {e}", exc_info=True)
