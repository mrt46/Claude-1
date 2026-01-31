"""
Simple Clean Dashboard - Replaces broken Rich dashboard.

Single panel, clear text, no complex layouts.
"""

import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

from src.core.logger import get_logger

logger = get_logger(__name__)


class SimpleDashboard:
    """
    Simple text-based dashboard.

    No complex layouts, just clear text output.
    Updates every 5 seconds to avoid clutter.
    """

    def __init__(self, database=None, optimization_agent=None):
        """Initialize simple dashboard."""
        self.database = database
        self.optimization_agent = optimization_agent
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # State
        self.bot_status = "🟡 Initializing"
        self.balance = 0.0
        self.daily_pnl = 0.0
        self.total_signals = 0
        self.approved_trades = 0
        self.last_analysis_time: Optional[datetime] = None
        self.last_analysis_result: Optional[Dict] = None
        self.active_positions: List[Dict] = []
        self.recent_trades: List[Dict] = []
        self.daily_stats: Dict = {}

        logger.info("SimpleDashboard initialized")

    def start(self) -> None:
        """Start dashboard in background."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info("SimpleDashboard started")

    def stop(self) -> None:
        """Stop dashboard."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        logger.info("SimpleDashboard stopped")

    def _run(self) -> None:
        """Main dashboard loop."""
        print("\n" + "="*80)
        print("TRADING BOT DASHBOARD (Simple Mode)")
        print("="*80)
        print("Dashboard updates every 5 seconds")
        print("Press Ctrl+C to stop bot")
        print("="*80 + "\n")

        while self.running:
            try:
                self._print_status()
                time.sleep(5)  # Update every 5 seconds
            except Exception as e:
                logger.error(f"Dashboard error: {e}")

    def _print_status(self) -> None:
        """Print current status."""
        now = datetime.now().strftime("%H:%M:%S")

        # Clear line and print status
        status = (
            f"\r[{now}] {self.bot_status} | "
            f"Balance: ${self.balance:.2f} | "
            f"Signals: {self.total_signals} | "
            f"Trades: {self.approved_trades}"
        )

        # Add last analysis info
        if self.last_analysis_result:
            buy_score = self.last_analysis_result.get('buy_score', 0)
            sell_score = self.last_analysis_result.get('sell_score', 0)
            max_score = self.last_analysis_result.get('max_score', 10)
            min_score = self.last_analysis_result.get('min_score', 7)

            status += f" | Last: BUY {buy_score:.1f}/{max_score:.1f} (min:{min_score:.1f}), SELL {sell_score:.1f}/{max_score:.1f}"

        print(status, end='', flush=True)

    # Update methods (same interface as TerminalDashboard)

    def update_account_info(self, balance: float, pnl: float, pnl_percent: float) -> None:
        """Update account info."""
        self.balance = balance
        self.daily_pnl = pnl

    def update_bot_status(self, status: str) -> None:
        """Update bot status."""
        self.bot_status = status

    def update_analysis_result(
        self,
        symbol: str,
        buy_score: float,
        sell_score: float,
        max_score: float,
        min_score: float,
        signal_generated: bool,
        min_sell_score: float = None
    ) -> None:
        """Update last analysis result."""
        self.last_analysis_time = datetime.now()
        self.last_analysis_result = {
            'symbol': symbol,
            'buy_score': buy_score,
            'sell_score': sell_score,
            'max_score': max_score,
            'min_score': min_score,
            'min_sell_score': min_sell_score or min_score,
            'signal_generated': signal_generated,
            'timestamp': datetime.now()
        }

    def add_signal(self, signal: Dict) -> None:
        """Add new signal."""
        self.total_signals += 1

    def update_trade_result(self, approved: bool) -> None:
        """Update trade result."""
        if approved:
            self.approved_trades += 1

    def update_positions(self, positions: List[Dict]) -> None:
        """Update active positions."""
        self.active_positions = positions

    def update_trades(self, trades: List[Dict]) -> None:
        """Update recent trades."""
        self.recent_trades = trades

    def update_daily_stats(self, stats: Dict) -> None:
        """Update daily stats."""
        self.daily_stats = stats

    def update_wallet_info(self, portfolio: Dict) -> None:
        """Update wallet info."""
        pass  # Not displayed in simple mode

    def update_system_status(self, status: Dict) -> None:
        """Update system status."""
        pass  # Not displayed in simple mode

    def increment_error(self) -> None:
        """Increment error count."""
        pass  # Not displayed in simple mode

    def is_running(self) -> bool:
        """Check if running."""
        return self.running
