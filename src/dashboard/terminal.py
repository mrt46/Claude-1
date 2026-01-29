"""
Terminal Dashboard using Rich library.

Real-time monitoring of trading bot performance.
Non-intrusive: Runs in separate thread, doesn't modify existing code.
"""

import asyncio
import threading
from datetime import datetime
from typing import Dict, List, Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.core.logger import get_logger

logger = get_logger(__name__)


class TerminalDashboard:
    """
    Terminal-based real-time dashboard.
    
    Features:
    - Trading performance metrics
    - Active positions
    - System health
    - Recent signals
    - Market data status
    
    Non-intrusive: Can be started/stopped independently.
    """
    
    def __init__(self):
        """Initialize terminal dashboard."""
        self.console = Console()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
        # State data (updated by bot)
        self.account_balance: float = 0.0
        self.daily_pnl: float = 0.0
        self.daily_pnl_percent: float = 0.0
        self.active_positions: List[Dict] = []
        self.recent_signals: List[Dict] = []
        self.system_status: Dict = {
            'websocket_connected': False,
            'database_connected': False,
            'last_update': None
        }
        self.error_count: int = 0
        self.total_signals: int = 0
        self.approved_trades: int = 0
        self.rejected_trades: int = 0
        
        # Bot activity tracking
        self.bot_status: str = "🟡 Initializing"
        self.last_analysis_time: Optional[datetime] = None
        self.analysis_count: int = 0
        self.last_analysis_result: Optional[Dict] = None
        self.last_symbol_analyzed: Optional[str] = None
        self.heartbeat_time: Optional[datetime] = None
        
        # Wallet/Portfolio data
        self.wallet_data: Optional[Dict] = None
    
    def update_account_info(self, balance: float, pnl: float, pnl_percent: float) -> None:
        """Update account information."""
        self.account_balance = balance
        self.daily_pnl = pnl
        self.daily_pnl_percent = pnl_percent
    
    def update_wallet_info(self, portfolio: Dict) -> None:
        """
        Update wallet/portfolio information.
        
        Args:
            portfolio: Portfolio dictionary with balances and values
                {
                    'total_value_usdt': float,
                    'balances': List[Dict],
                    'bnb_value_usdt': float,
                    'usdt_balance': float
                }
        """
        self.wallet_data = portfolio
    
    def update_positions(self, positions: List[Dict]) -> None:
        """Update active positions."""
        self.active_positions = positions
    
    def add_signal(self, signal: Dict) -> None:
        """Add new signal to recent signals."""
        self.recent_signals.insert(0, signal)
        self.total_signals += 1
        # Keep only last 10 signals
        if len(self.recent_signals) > 10:
            self.recent_signals = self.recent_signals[:10]
    
    def update_trade_result(self, approved: bool) -> None:
        """Update trade approval/rejection count."""
        if approved:
            self.approved_trades += 1
        else:
            self.rejected_trades += 1
    
    def update_system_status(self, status: Dict) -> None:
        """Update system status."""
        self.system_status.update(status)
        self.system_status['last_update'] = datetime.now()
    
    def increment_error(self) -> None:
        """Increment error count."""
        self.error_count += 1
    
    def update_bot_status(self, status: str) -> None:
        """Update bot status."""
        self.bot_status = status
        self.heartbeat_time = datetime.now()
    
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
        self.analysis_count += 1
        self.last_symbol_analyzed = symbol
        # Use min_score as min_buy_score if min_sell_score not provided (backward compatibility)
        min_buy_score = min_score
        if min_sell_score is None:
            min_sell_score = min_score
        self.last_analysis_result = {
            'symbol': symbol,
            'buy_score': buy_score,
            'sell_score': sell_score,
            'max_score': max_score,
            'min_score': min_buy_score,
            'min_sell_score': min_sell_score,
            'signal_generated': signal_generated,
            'timestamp': datetime.now()
        }
        self.heartbeat_time = datetime.now()
    
    def _create_performance_panel(self) -> Panel:
        """Create performance metrics panel."""
        table = Table.grid(padding=1)
        table.add_column(style="cyan", justify="right")
        table.add_column(style="magenta")
        
        # Account info
        pnl_color = "green" if self.daily_pnl >= 0 else "red"
        pnl_sign = "+" if self.daily_pnl >= 0 else ""
        
        table.add_row("Balance:", f"{self.account_balance:,.2f} USDT")
        table.add_row("Daily PnL:", f"[{pnl_color}]{pnl_sign}{self.daily_pnl:,.2f} USDT[/{pnl_color}]")
        table.add_row("Daily PnL %:", f"[{pnl_color}]{pnl_sign}{self.daily_pnl_percent:.2f}%[/{pnl_color}]")
        table.add_row("", "")
        table.add_row("Total Signals:", str(self.total_signals))
        table.add_row("Approved:", f"[green]{self.approved_trades}[/green]")
        table.add_row("Rejected:", f"[red]{self.rejected_trades}[/red]")
        
        if self.total_signals > 0:
            approval_rate = (self.approved_trades / self.total_signals) * 100
            table.add_row("Approval Rate:", f"{approval_rate:.1f}%")
        
        return Panel(table, title="[bold cyan]Performance[/bold cyan]", border_style="cyan")
    
    def _create_positions_panel(self) -> Panel:
        """Create active positions panel."""
        if not self.active_positions:
            return Panel(
                Text("No active positions", justify="center", style="dim"),
                title="[bold yellow]Active Positions[/bold yellow]",
                border_style="yellow"
            )
        
        table = Table.grid(padding=1)
        table.add_column(style="cyan")
        table.add_column(style="magenta", justify="right")
        table.add_column(style="green", justify="right")
        table.add_column(style="red", justify="right")
        
        for pos in self.active_positions[:5]:  # Show max 5 positions
            symbol = pos.get('symbol', 'N/A')
            side = pos.get('side', 'N/A')
            entry = pos.get('entry_price', 0)
            qty = pos.get('quantity', 0)
            pnl = pos.get('unrealized_pnl', 0)
            pnl_percent = pos.get('unrealized_pnl_percent', 0)
            
            pnl_color = "green" if pnl >= 0 else "red"
            pnl_sign = "+" if pnl >= 0 else ""
            
            table.add_row(
                f"{symbol} {side}",
                f"@{entry:.2f}",
                f"Qty: {qty:.4f}",
                f"[{pnl_color}]{pnl_sign}{pnl:.2f} ({pnl_sign}{pnl_percent:.2f}%)[/{pnl_color}]"
            )
        
        return Panel(table, title="[bold yellow]Active Positions[/bold yellow]", border_style="yellow")
    
    def _create_signals_panel(self) -> Panel:
        """Create recent signals panel."""
        if not self.recent_signals:
            return Panel(
                Text("No signals yet", justify="center", style="dim"),
                title="[bold green]Recent Signals[/bold green]",
                border_style="green"
            )
        
        table = Table.grid(padding=1)
        table.add_column(style="cyan")
        table.add_column(style="magenta", justify="right")
        table.add_column(style="green", justify="right")
        
        for signal in self.recent_signals[:5]:  # Show max 5 signals
            symbol = signal.get('symbol', 'N/A')
            side = signal.get('side', 'N/A')
            price = signal.get('entry_price', 0)
            confidence = signal.get('confidence', 0)
            timestamp = signal.get('timestamp', 'N/A')
            
            if isinstance(timestamp, datetime):
                timestamp = timestamp.strftime("%H:%M:%S")
            
            side_color = "green" if side == "BUY" else "red"
            
            table.add_row(
                f"{symbol}",
                f"[{side_color}]{side}[/{side_color}] @ {price:.2f}",
                f"Conf: {confidence:.2f} | {timestamp}"
            )
        
        return Panel(table, title="[bold green]Recent Signals[/bold green]", border_style="green")
    
    def _create_system_panel(self) -> Panel:
        """Create system status panel."""
        table = Table.grid(padding=1)
        table.add_column(style="cyan", justify="right")
        table.add_column(style="magenta")
        
        ws_status = "🟢 Connected" if self.system_status.get('websocket_connected') else "🔴 Disconnected"
        db_status = "🟢 Connected" if self.system_status.get('database_connected') else "🔴 Disconnected"
        
        table.add_row("Bot Status:", self.bot_status)
        table.add_row("WebSocket:", ws_status)
        table.add_row("Database:", db_status)
        table.add_row("Errors:", f"[red]{self.error_count}[/red]")
        
        last_update = self.system_status.get('last_update')
        if last_update:
            if isinstance(last_update, datetime):
                table.add_row("Last Update:", last_update.strftime("%H:%M:%S"))
            else:
                table.add_row("Last Update:", str(last_update))
        
        return Panel(table, title="[bold blue]System Status[/bold blue]", border_style="blue")
    
    def _create_activity_panel(self) -> Panel:
        """Create bot activity panel."""
        table = Table.grid(padding=1)
        table.add_column(style="cyan", justify="right")
        table.add_column(style="magenta")
        
        # Bot status
        table.add_row("Status:", self.bot_status)
        
        # Analysis info
        if self.last_analysis_time:
            time_diff = (datetime.now() - self.last_analysis_time).total_seconds()
            if time_diff < 60:
                time_str = f"{int(time_diff)}s ago"
            elif time_diff < 3600:
                time_str = f"{int(time_diff/60)}m ago"
            else:
                time_str = f"{int(time_diff/3600)}h ago"
            table.add_row("Last Analysis:", time_str)
        else:
            table.add_row("Last Analysis:", "Never")
        
        table.add_row("Total Analyses:", str(self.analysis_count))
        
        if self.last_symbol_analyzed:
            table.add_row("Last Symbol:", self.last_symbol_analyzed)
        
        # Last analysis result
        if self.last_analysis_result:
            result = self.last_analysis_result
            buy_score = result['buy_score']
            sell_score = result['sell_score']
            max_score = result['max_score']
            min_score = result['min_score']
            
            # Score colors
            buy_color = "green" if buy_score >= min_score else "yellow"
            sell_color = "red" if sell_score >= min_score else "yellow"
            
            table.add_row("", "")
            table.add_row("[bold]Last Scores:[/bold]", "")
            # Get separate thresholds if available
            min_buy_score = result.get('min_score', result.get('min_buy_score', min_score))
            min_sell_score = result.get('min_sell_score', min_buy_score)
            
            # Update colors based on respective thresholds
            buy_color = "green" if buy_score >= min_buy_score else "yellow"
            sell_color = "red" if sell_score >= min_sell_score else "yellow"
            
            table.add_row("  BUY:", f"[{buy_color}]{buy_score:.1f}/{max_score:.1f}[/{buy_color}] (min: {min_buy_score:.1f})")
            table.add_row("  SELL:", f"[{sell_color}]{sell_score:.1f}/{max_score:.1f}[/{sell_color}] (min: {min_sell_score:.1f})")
            
            if result['signal_generated']:
                table.add_row("  Result:", "[green]✓ Signal Generated[/green]")
            else:
                table.add_row("  Result:", "[yellow]✗ No Signal[/yellow]")
        
        # Heartbeat
        if self.heartbeat_time:
            heartbeat_diff = (datetime.now() - self.heartbeat_time).total_seconds()
            if heartbeat_diff < 120:  # 2 minutes
                heartbeat_status = f"🟢 {int(heartbeat_diff)}s ago"
            else:
                heartbeat_status = f"🔴 {int(heartbeat_diff/60)}m ago"
            table.add_row("", "")
            table.add_row("Heartbeat:", heartbeat_status)
        
        return Panel(table, title="[bold magenta]Bot Activity[/bold magenta]", border_style="magenta")
    
    def _create_wallet_panel(self) -> Panel:
        """Create Binance-style wallet panel showing all coins and values."""
        if not self.wallet_data:
            return Panel(
                Text("Loading wallet...", justify="center", style="dim"),
                title="[bold yellow]Wallet[/bold yellow]",
                border_style="yellow"
            )
        
        table = Table.grid(padding=1)
        table.add_column(style="cyan")  # Asset
        table.add_column(style="magenta", justify="right")  # Amount
        table.add_column(style="green", justify="right")  # Value USDT
        
        balances = self.wallet_data.get('balances', [])
        
        if not balances:
            return Panel(
                Text("No balances", justify="center", style="dim"),
                title="[bold yellow]Wallet[/bold yellow]",
                border_style="yellow"
            )
        
        # Sort by value (descending) and show top 10
        sorted_balances = sorted(
            balances,
            key=lambda x: x.get('value_usdt', 0),
            reverse=True
        )[:10]
        
        for balance in sorted_balances:
            asset = balance.get('asset', 'N/A')
            free = balance.get('free', 0.0)
            value_usdt = balance.get('value_usdt', 0.0)
            
            # Format amount (remove trailing zeros)
            amount_str = f"{free:.8f}".rstrip('0').rstrip('.')
            if '.' not in amount_str:
                amount_str = f"{free:.2f}"
            
            # Special formatting for BNB
            if asset == 'BNB':
                bnb_value = value_usdt
                min_bnb = 10.0
                if bnb_value >= min_bnb:
                    status = "✅"
                    asset_display = f"{asset} {status}"
                elif bnb_value >= min_bnb * 0.8:
                    status = "⚠️"
                    asset_display = f"{asset} {status}"
                else:
                    status = "🔴"
                    asset_display = f"{asset} {status}"
            else:
                asset_display = asset
            
            # Color code based on value
            if value_usdt >= 1000:
                value_color = "bold green"
            elif value_usdt >= 100:
                value_color = "green"
            else:
                value_color = "white"
            
            table.add_row(
                asset_display,
                amount_str,
                f"[{value_color}]€{value_usdt:,.2f}[/{value_color}]"
            )
        
        # Total portfolio value
        total_value = self.wallet_data.get('total_value_usdt', 0.0)
        table.add_row("", "", "")
        table.add_row(
            "[bold]Total Portfolio:[/bold]",
            "",
            f"[bold green]€{total_value:,.2f}[/bold green]"
        )
        
        # BNB Status
        bnb_value = self.wallet_data.get('bnb_value_usdt', 0.0)
        min_bnb = 10.0
        if bnb_value >= min_bnb:
            bnb_status = f"✅ OK (€{bnb_value:.2f})"
            bnb_color = "green"
        elif bnb_value >= min_bnb * 0.8:
            bnb_status = f"⚠️ Low (€{bnb_value:.2f})"
            bnb_color = "yellow"
        else:
            bnb_status = f"🔴 Critical (€{bnb_value:.2f})"
            bnb_color = "red"
        
        table.add_row("", "", "")
        table.add_row(
            "[bold]BNB Status:[/bold]",
            "",
            f"[{bnb_color}]{bnb_status}[/{bnb_color}]"
        )
        
        return Panel(table, title="[bold yellow]Wallet[/bold yellow]", border_style="yellow")
    
    def _generate_layout(self) -> Layout:
        """Generate dashboard layout."""
        layout = Layout()
        
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        
        layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )
        
        layout["left"].split_column(
            Layout(name="performance"),
            Layout(name="wallet"),
            Layout(name="positions")
        )
        
        layout["right"].split_column(
            Layout(name="signals"),
            Layout(name="activity"),
            Layout(name="system")
        )
        
        # Header
        header_text = Text("🏛️ INSTITUTIONAL TRADING BOT - LIVE DASHBOARD", style="bold white on blue", justify="center")
        layout["header"].update(Panel(header_text, border_style="blue"))
        
        # Main panels
        layout["performance"].update(self._create_performance_panel())
        layout["wallet"].update(self._create_wallet_panel())
        layout["positions"].update(self._create_positions_panel())
        layout["signals"].update(self._create_signals_panel())
        layout["activity"].update(self._create_activity_panel())
        layout["system"].update(self._create_system_panel())
        
        # Footer
        footer_text = Text(
            f"Press Ctrl+C to stop | Bot Status: {'🟢 Running' if self.running else '🔴 Stopped'}",
            style="dim",
            justify="center"
        )
        layout["footer"].update(Panel(footer_text, border_style="dim"))
        
        return layout
    
    def _run_dashboard(self) -> None:
        """Run dashboard in a loop."""
        try:
            # Use screen=False to allow logs to be visible alongside dashboard
            # This provides better debugging while still showing the dashboard
            with Live(self._generate_layout(), refresh_per_second=2, screen=False, vertical_overflow="visible") as live:
                while self.running:
                    live.update(self._generate_layout())
                    threading.Event().wait(0.5)  # Update every 0.5 seconds
        except KeyboardInterrupt:
            self.running = False
        except Exception as e:
            logger.error(f"Dashboard error: {e}")
            self.running = False
    
    def start(self) -> None:
        """Start dashboard in separate thread."""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_dashboard, daemon=True)
        self.thread.start()
        logger.info("Terminal dashboard started")
    
    def stop(self) -> None:
        """Stop dashboard."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        logger.info("Terminal dashboard stopped")
    
    def is_running(self) -> bool:
        """Check if dashboard is running."""
        return self.running
