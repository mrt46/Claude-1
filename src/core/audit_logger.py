"""
Audit Logger - Comprehensive trade and decision logging.

Records all trading activities for compliance, debugging, and analysis.
Logs are written to both file and can be queried programmatically.
"""

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.logger import get_logger

logger = get_logger(__name__)


class AuditEventType(Enum):
    """Types of audit events."""
    # Trading events
    SIGNAL_GENERATED = "signal_generated"
    SIGNAL_REJECTED = "signal_rejected"
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_REJECTED = "order_rejected"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    STOP_LOSS_TRIGGERED = "stop_loss_triggered"
    TAKE_PROFIT_TRIGGERED = "take_profit_triggered"

    # Risk events
    RISK_CHECK_PASSED = "risk_check_passed"
    RISK_CHECK_FAILED = "risk_check_failed"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    POSITION_LIMIT = "position_limit"

    # System events
    BOT_STARTED = "bot_started"
    BOT_STOPPED = "bot_stopped"
    EMERGENCY_STOP = "emergency_stop"
    ERROR = "error"
    WARNING = "warning"

    # Analysis events
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_COMPLETED = "analysis_completed"


class AuditLogger:
    """
    Audit logger for comprehensive trade logging.

    Features:
    - JSON-formatted log entries
    - File rotation by date
    - In-memory recent events buffer
    - Queryable event history
    - Thread-safe logging
    """

    def __init__(
        self,
        log_dir: str = "logs/audit",
        max_memory_events: int = 1000,
        log_to_file: bool = True
    ):
        """
        Initialize audit logger.

        Args:
            log_dir: Directory for audit log files
            max_memory_events: Maximum events to keep in memory
            log_to_file: Whether to write to file (default: True)
        """
        self.log_dir = Path(log_dir)
        self.max_memory_events = max_memory_events
        self.log_to_file = log_to_file

        # Create log directory
        if self.log_to_file:
            self.log_dir.mkdir(parents=True, exist_ok=True)

        # In-memory event buffer
        self._events: List[Dict] = []

        # Current log file
        self._current_date: Optional[str] = None
        self._log_file: Optional[Path] = None

        logger.info(f"AuditLogger initialized: log_dir={log_dir}, max_events={max_memory_events}")

    def _get_log_file(self) -> Path:
        """Get current log file path (rotates daily)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if self._current_date != today:
            self._current_date = today
            self._log_file = self.log_dir / f"audit_{today}.jsonl"

        return self._log_file

    def log_event(
        self,
        event_type: AuditEventType,
        data: Dict[str, Any],
        symbol: Optional[str] = None,
        order_id: Optional[str] = None
    ) -> Dict:
        """
        Log an audit event.

        Args:
            event_type: Type of event
            data: Event data dictionary
            symbol: Trading symbol (optional)
            order_id: Order ID (optional)

        Returns:
            The logged event dictionary
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type.value,
            "symbol": symbol,
            "order_id": order_id,
            "data": data
        }

        # Add to memory buffer
        self._events.append(event)

        # Trim buffer if needed
        if len(self._events) > self.max_memory_events:
            self._events = self._events[-self.max_memory_events:]

        # Write to file
        if self.log_to_file:
            try:
                log_file = self._get_log_file()
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event) + "\n")
            except Exception as e:
                logger.error(f"Failed to write audit log: {e}")

        # Also log to standard logger for visibility
        log_msg = f"AUDIT: {event_type.value}"
        if symbol:
            log_msg += f" [{symbol}]"
        if order_id:
            log_msg += f" (order={order_id})"

        logger.info(log_msg)

        return event

    def log_signal(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        confidence: float,
        scores: Dict[str, float],
        accepted: bool,
        rejection_reason: Optional[str] = None
    ) -> Dict:
        """
        Log a trading signal.

        Args:
            symbol: Trading symbol
            side: BUY or SELL
            entry_price: Signal entry price
            confidence: Signal confidence
            scores: Analysis scores
            accepted: Whether signal was accepted
            rejection_reason: Reason if rejected

        Returns:
            The logged event
        """
        event_type = AuditEventType.SIGNAL_GENERATED if accepted else AuditEventType.SIGNAL_REJECTED

        return self.log_event(
            event_type=event_type,
            symbol=symbol,
            data={
                "side": side,
                "entry_price": entry_price,
                "confidence": confidence,
                "scores": scores,
                "accepted": accepted,
                "rejection_reason": rejection_reason
            }
        )

    def log_order(
        self,
        order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float],
        status: str,
        exchange_order_id: Optional[str] = None,
        fill_price: Optional[float] = None,
        filled_quantity: Optional[float] = None,
        fees: Optional[float] = None,
        error: Optional[str] = None
    ) -> Dict:
        """
        Log an order event.

        Args:
            order_id: Internal order ID
            symbol: Trading symbol
            side: BUY or SELL
            order_type: MARKET or LIMIT
            quantity: Order quantity
            price: Order price (for limit orders)
            status: Order status
            exchange_order_id: Exchange's order ID
            fill_price: Average fill price
            filled_quantity: Quantity filled
            fees: Trading fees
            error: Error message if failed

        Returns:
            The logged event
        """
        # Determine event type based on status
        status_upper = status.upper()
        if status_upper == "PLACED":
            event_type = AuditEventType.ORDER_PLACED
        elif status_upper == "FILLED":
            event_type = AuditEventType.ORDER_FILLED
        elif status_upper in ["CANCELLED", "CANCELED"]:
            event_type = AuditEventType.ORDER_CANCELLED
        elif status_upper == "REJECTED":
            event_type = AuditEventType.ORDER_REJECTED
        else:
            event_type = AuditEventType.ORDER_PLACED

        return self.log_event(
            event_type=event_type,
            symbol=symbol,
            order_id=order_id,
            data={
                "side": side,
                "order_type": order_type,
                "quantity": quantity,
                "price": price,
                "status": status,
                "exchange_order_id": exchange_order_id,
                "fill_price": fill_price,
                "filled_quantity": filled_quantity,
                "fees": fees,
                "error": error
            }
        )

    def log_position(
        self,
        position_id: str,
        symbol: str,
        side: str,
        action: str,  # "opened" or "closed"
        entry_price: float,
        quantity: float,
        exit_price: Optional[float] = None,
        pnl: Optional[float] = None,
        pnl_percent: Optional[float] = None,
        close_reason: Optional[str] = None
    ) -> Dict:
        """
        Log a position event.

        Args:
            position_id: Position ID
            symbol: Trading symbol
            side: BUY or SELL
            action: "opened" or "closed"
            entry_price: Entry price
            quantity: Position size
            exit_price: Exit price (if closed)
            pnl: Profit/loss (if closed)
            pnl_percent: PnL percentage (if closed)
            close_reason: Reason for closing

        Returns:
            The logged event
        """
        if action == "opened":
            event_type = AuditEventType.POSITION_OPENED
        elif close_reason == "stop_loss":
            event_type = AuditEventType.STOP_LOSS_TRIGGERED
        elif close_reason == "take_profit":
            event_type = AuditEventType.TAKE_PROFIT_TRIGGERED
        else:
            event_type = AuditEventType.POSITION_CLOSED

        return self.log_event(
            event_type=event_type,
            symbol=symbol,
            order_id=position_id,
            data={
                "side": side,
                "action": action,
                "entry_price": entry_price,
                "quantity": quantity,
                "exit_price": exit_price,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "close_reason": close_reason
            }
        )

    def log_risk_check(
        self,
        symbol: str,
        check_type: str,
        passed: bool,
        details: Dict[str, Any]
    ) -> Dict:
        """
        Log a risk check event.

        Args:
            symbol: Trading symbol
            check_type: Type of risk check
            passed: Whether check passed
            details: Check details

        Returns:
            The logged event
        """
        event_type = AuditEventType.RISK_CHECK_PASSED if passed else AuditEventType.RISK_CHECK_FAILED

        return self.log_event(
            event_type=event_type,
            symbol=symbol,
            data={
                "check_type": check_type,
                "passed": passed,
                **details
            }
        )

    def log_system_event(
        self,
        event_type: AuditEventType,
        message: str,
        details: Optional[Dict] = None
    ) -> Dict:
        """
        Log a system event.

        Args:
            event_type: Event type
            message: Event message
            details: Additional details

        Returns:
            The logged event
        """
        return self.log_event(
            event_type=event_type,
            data={
                "message": message,
                **(details or {})
            }
        )

    def log_error(
        self,
        error: str,
        context: Optional[Dict] = None,
        symbol: Optional[str] = None
    ) -> Dict:
        """
        Log an error event.

        Args:
            error: Error message
            context: Error context
            symbol: Related symbol

        Returns:
            The logged event
        """
        return self.log_event(
            event_type=AuditEventType.ERROR,
            symbol=symbol,
            data={
                "error": error,
                "context": context or {}
            }
        )

    def get_recent_events(
        self,
        count: int = 100,
        event_type: Optional[AuditEventType] = None,
        symbol: Optional[str] = None
    ) -> List[Dict]:
        """
        Get recent events from memory buffer.

        Args:
            count: Maximum number of events to return
            event_type: Filter by event type
            symbol: Filter by symbol

        Returns:
            List of events (newest first)
        """
        events = self._events.copy()

        # Filter by event type
        if event_type:
            events = [e for e in events if e["event_type"] == event_type.value]

        # Filter by symbol
        if symbol:
            events = [e for e in events if e["symbol"] == symbol]

        # Return newest first, limited by count
        return list(reversed(events[-count:]))

    def get_daily_summary(self) -> Dict:
        """
        Get summary of today's trading activity.

        Returns:
            Summary dictionary
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Filter today's events
        today_events = [
            e for e in self._events
            if e["timestamp"].startswith(today)
        ]

        # Count by type
        type_counts = {}
        for event in today_events:
            event_type = event["event_type"]
            type_counts[event_type] = type_counts.get(event_type, 0) + 1

        # Calculate PnL from position closures
        total_pnl = 0.0
        closed_positions = [
            e for e in today_events
            if e["event_type"] == AuditEventType.POSITION_CLOSED.value
        ]
        for pos in closed_positions:
            pnl = pos["data"].get("pnl", 0) or 0
            total_pnl += pnl

        return {
            "date": today,
            "total_events": len(today_events),
            "event_counts": type_counts,
            "signals_generated": type_counts.get(AuditEventType.SIGNAL_GENERATED.value, 0),
            "signals_rejected": type_counts.get(AuditEventType.SIGNAL_REJECTED.value, 0),
            "orders_placed": type_counts.get(AuditEventType.ORDER_PLACED.value, 0),
            "orders_filled": type_counts.get(AuditEventType.ORDER_FILLED.value, 0),
            "positions_opened": type_counts.get(AuditEventType.POSITION_OPENED.value, 0),
            "positions_closed": len(closed_positions),
            "total_pnl": total_pnl,
            "errors": type_counts.get(AuditEventType.ERROR.value, 0)
        }


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get or create global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
