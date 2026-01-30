"""
Main application entry point for the trading bot.

This is the orchestrator that ties all layers together.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from src.core.config import Config
from src.core.emergency_controller import EmergencyController
from src.core.exchange import BinanceExchange
from src.core.logger import get_logger
from src.core.position_monitor import PositionMonitor
from src.dashboard.terminal import TerminalDashboard
from src.data.database import RedisClient, TimescaleDBClient
from src.data.market_data import MarketDataManager
from src.execution.lifecycle import OrderLifecycleManager, OrderStatus
from src.execution.router import SmartOrderRouter
from src.risk.manager import RiskManager
from src.strategies.institutional import InstitutionalStrategy

logger = get_logger(__name__)


class TradingBot:
    """
    Main trading bot orchestrator.
    
    Coordinates all layers:
    - Data acquisition
    - Analysis
    - Strategy
    - Risk management
    - Execution
    """
    
    def __init__(self, config_path: Path = None):
        """
        Initialize trading bot.
        
        Args:
            config_path: Optional path to .env file
        """
        self.config = Config(config_path)
        self.logger = get_logger("TradingBot")
        
        # Initialize components
        self.market_data = MarketDataManager(testnet=self.config.exchange.testnet)
        self.timescaledb = TimescaleDBClient(
            host=self.config.database.timescaledb_host,
            port=self.config.database.timescaledb_port,
            database=self.config.database.timescaledb_database,
            user=self.config.database.timescaledb_user,
            password=self.config.database.timescaledb_password
        )
        self.redis = RedisClient(
            host=self.config.database.redis_host,
            port=self.config.database.redis_port,
            password=self.config.database.redis_password,
            db=self.config.database.redis_db
        )
        
        # Initialize strategy
        self.strategy = InstitutionalStrategy({
            'min_score': self.config.strategy.min_score,
            'min_buy_score': self.config.strategy.min_buy_score,
            'min_sell_score': self.config.strategy.min_sell_score,
            'weights': self.config.strategy.weights
        })
        self.strategy.set_market_data_manager(self.market_data)
        
        # Initialize risk manager
        self.risk_manager = RiskManager(
            max_positions=self.config.risk.max_positions,
            max_daily_loss_percent=self.config.risk.max_daily_loss_percent,
            max_drawdown_percent=self.config.risk.max_drawdown_percent,
            max_symbol_exposure_percent=self.config.risk.max_symbol_exposure_percent,
            risk_per_trade_percent=self.config.risk.risk_per_trade_percent,
            max_slippage_percent=self.config.risk.max_slippage_percent,
            min_liquidity_usdt=self.config.risk.min_liquidity_usdt,
            min_usdt_reserve=self.config.risk.min_usdt_reserve
        )
        
        # Initialize execution components
        self.exchange = BinanceExchange(
            api_key=self.config.exchange.api_key,
            api_secret=self.config.exchange.api_secret,
            testnet=self.config.exchange.testnet
        )
        self.order_router = SmartOrderRouter()
        self.order_lifecycle = OrderLifecycleManager()
        
        # Initialize dashboard (optional, non-intrusive)
        self.dashboard: Optional[TerminalDashboard] = None
        self.dashboard_enabled = True  # Can be disabled via config

        # Position monitor for SL/TP enforcement (initialized in initialize())
        self.position_monitor: Optional[PositionMonitor] = None

        # Emergency controller for crisis situations (initialized in initialize())
        self.emergency_controller: Optional[EmergencyController] = None

        self.running = False
    
    async def _start_websocket_streams(self) -> None:
        """
        Start WebSocket streams for real-time market data.
        
        Connects to:
        - Kline streams (for OHLCV updates)
        - Order book streams (for real-time order book)
        - Trade streams (for CVD calculation)
        """
        try:
            ws_connected_count = 0
            total_streams = len(self.config.trading.symbols) * 3  # 3 streams per symbol
            
            # Validate symbols before connecting WebSocket streams
            valid_symbols = []
            for symbol in self.config.trading.symbols:
                try:
                    # Quick validation: try to get price for symbol
                    price = await self.market_data.get_current_price(symbol)
                    if price is None:
                        self.logger.warning(f"Skipping {symbol}: Invalid symbol or not available on Binance")
                        continue
                    valid_symbols.append(symbol)
                except Exception as e:
                    self.logger.warning(f"Skipping {symbol}: Validation failed - {e}")
                    continue
            
            if not valid_symbols:
                self.logger.warning("No valid symbols found for WebSocket streams")
                return
            
            self.logger.info(f"Validated {len(valid_symbols)}/{len(self.config.trading.symbols)} symbols for WebSocket streams")
            
            for symbol in valid_symbols:
                # Create callbacks with proper closure
                def create_kline_callback(sym: str):
                    async def callback(data: Dict):
                        """Handle kline updates."""
                        try:
                            # Check if this is a connection status update
                            if data.get('type') == 'connection_established':
                                if self.dashboard:
                                    self.dashboard.update_system_status({
                                        'websocket_connected': True,
                                        'last_update': datetime.now()
                                    })
                            elif data.get('k', {}).get('x'):  # Candle closed
                                if self.dashboard:
                                    self.dashboard.update_system_status({
                                        'websocket_connected': True,
                                        'last_update': datetime.now()
                                    })
                        except Exception as e:
                            logger.debug(f"Kline callback error for {sym}: {e}")
                    return callback
                
                def create_orderbook_callback(sym: str):
                    async def callback(data: Dict):
                        """Handle order book updates."""
                        try:
                            # Update connection status on any message
                            if self.dashboard:
                                self.dashboard.update_system_status({
                                    'websocket_connected': True,
                                    'last_update': datetime.now()
                                })
                        except Exception as e:
                            logger.debug(f"Orderbook callback error for {sym}: {e}")
                    return callback
                
                def create_trade_callback(sym: str):
                    async def callback(data: Dict):
                        """Handle trade updates."""
                        try:
                            if self.dashboard:
                                self.dashboard.update_system_status({
                                    'websocket_connected': True,
                                    'last_update': datetime.now()
                                })
                        except Exception as e:
                            logger.debug(f"Trade callback error for {sym}: {e}")
                    return callback
                
                # Connect streams
                try:
                    await self.market_data.ws_manager.connect_kline_stream(
                        symbol=symbol,
                        interval="1m",
                        callback=create_kline_callback(symbol)
                    )
                    ws_connected_count += 1
                    
                    await self.market_data.ws_manager.connect_orderbook_stream(
                        symbol=symbol,
                        callback=create_orderbook_callback(symbol),
                        update_speed="100ms"
                    )
                    ws_connected_count += 1
                    
                    await self.market_data.ws_manager.connect_trade_stream(
                        symbol=symbol,
                        callback=create_trade_callback(symbol)
                    )
                    ws_connected_count += 1
                    
                    self.logger.info(f"WebSocket streams started for {symbol}")
                    
                except Exception as e:
                    self.logger.warning(f"Failed to start WebSocket for {symbol}: {e}")
            
            # Wait a bit for connections to establish (WebSocket connections are async)
            await asyncio.sleep(5)  # Give WebSocket more time to connect
            
            # Check actual connection status multiple times (connections are async)
            ws_connected = False
            connected_streams = []
            for check_attempt in range(3):
                await asyncio.sleep(2)  # Wait between checks
                ws_connected = self.market_data.ws_manager.is_connected()
                connected_streams = self.market_data.ws_manager.get_connected_streams()
                if ws_connected and len(connected_streams) > 0:
                    break
            
            if ws_connected and len(connected_streams) > 0:
                self.logger.info(f"✅ WebSocket streams active: {len(connected_streams)} streams connected")
                self.logger.info(f"Connected streams: {', '.join(connected_streams[:5])}{'...' if len(connected_streams) > 5 else ''}")
            else:
                self.logger.warning(f"⚠️ WebSocket streams not connected: {len(connected_streams)}/{total_streams} streams")
                self.logger.warning("Bot will continue with REST API only (real-time updates may be delayed)")
            
            # Update dashboard based on connection status
            if self.dashboard:
                db_connected = False
                try:
                    if self.timescaledb.pool and self.timescaledb.is_connected():
                        # Quick check with timeout
                        try:
                            conn = await asyncio.wait_for(
                                self.timescaledb.pool.acquire(),
                                timeout=2.0
                            )
                            await self.timescaledb.pool.release(conn)
                            db_connected = True
                        except (asyncio.TimeoutError, Exception) as e:
                            self.logger.debug(f"Database connection check failed: {e}")
                            db_connected = False
                    else:
                        db_connected = False
                except Exception as e:
                    self.logger.debug(f"Database status check error: {e}")
                    db_connected = False
                
                # Also check Redis
                redis_connected = False
                if self.redis.client is not None:
                    try:
                        await asyncio.wait_for(
                            self.redis.client.ping(),
                            timeout=2.0
                        )
                        redis_connected = True
                    except (asyncio.TimeoutError, Exception) as e:
                        self.logger.debug(f"Redis connection check failed: {e}")
                        redis_connected = False
                
                # Database is connected if either TimescaleDB or Redis is connected
                any_db_connected = db_connected or redis_connected
                
                self.dashboard.update_system_status({
                    'websocket_connected': ws_connected,
                    'database_connected': any_db_connected,
                    'last_update': datetime.now()
                })
            
            if ws_connected:
                self.logger.info(f"WebSocket streams initialized ({ws_connected_count}/{total_streams} streams connected)")
            else:
                self.logger.warning("No WebSocket streams connected (continuing with REST API only)")
        
        except Exception as e:
            self.logger.warning(f"Failed to start WebSocket streams: {e} (continuing with REST API only)")
            if self.dashboard:
                self.dashboard.update_system_status({
                    'websocket_connected': False,
                    'last_update': datetime.now()
                })
    
    async def initialize(self) -> None:
        """Initialize database connections and exchange."""
        try:
            # Initialize databases (optional - can run without them)
            db_connected = False
            redis_connected = False
            
            # Try TimescaleDB
            try:
                db_connected = await self.timescaledb.connect()
            except Exception as e:
                self.logger.warning(f"TimescaleDB connection failed: {e}")
                db_connected = False
            
            # Try Redis
            try:
                redis_connected = await self.redis.connect()
            except Exception as e:
                self.logger.warning(f"Redis connection failed: {e}")
                redis_connected = False
            
            if db_connected and redis_connected:
                self.logger.info("✅ All database connections established")
            elif db_connected or redis_connected:
                self.logger.info(f"⚠️  Partial database connections (TimescaleDB: {db_connected}, Redis: {redis_connected})")
            else:
                self.logger.info("ℹ️  Running without databases (data won't be persisted, but bot will work)")
            
            # Initialize exchange
            await self.exchange.__aenter__()
            
            # Get initial account balance
            try:
                account_info = await self.exchange.get_account_info()
                usdt_balance = await self.exchange.get_balance("USDT")
                self.risk_manager.set_daily_start_balance(usdt_balance)
                self.logger.info(f"Account initialized. USDT Balance: {usdt_balance:.2f}")
            except Exception as e:
                self.logger.warning(f"Failed to get account info: {e}")
                usdt_balance = 10000.0  # Fallback
                self.risk_manager.set_daily_start_balance(usdt_balance)
            
            # Initialize dashboard (optional)
            if self.dashboard_enabled:
                try:
                    self.dashboard = TerminalDashboard()
                    self.dashboard.start()
                    self.dashboard.update_account_info(usdt_balance, 0.0, 0.0)
                    
                    # Initial portfolio update
                    try:
                        portfolio = await self.exchange.get_portfolio_summary()
                        self.dashboard.update_wallet_info(portfolio)
                    except Exception as e:
                        self.logger.warning(f"Failed to get initial portfolio: {e}")
                    
                    self.dashboard.update_system_status({
                        'websocket_connected': False,
                        'database_connected': True
                    })
                    self.logger.info("Terminal dashboard enabled")
                except Exception as e:
                    self.logger.warning(f"Failed to start dashboard: {e}")
                    self.dashboard = None
            
            # Start WebSocket connections for real-time data (with timeout protection)
            self.logger.info("Starting WebSocket streams...")
            try:
                await asyncio.wait_for(self._start_websocket_streams(), timeout=30.0)
                self.logger.info("WebSocket streams initialization complete")
            except asyncio.TimeoutError:
                self.logger.warning("WebSocket initialization timed out (continuing with REST API only)")
            except Exception as e:
                self.logger.warning(f"WebSocket initialization error: {e} (continuing with REST API only)")

            # Initialize and start position monitor for SL/TP enforcement
            self.position_monitor = PositionMonitor(
                risk_manager=self.risk_manager,
                exchange=self.exchange,
                order_lifecycle=self.order_lifecycle,
                market_data=self.market_data,
                check_interval=5.0,  # Check positions every 5 seconds
                trailing_stop_enabled=False,
                max_position_age_hours=None,  # No time limit
                adverse_spread_threshold=0.005  # 0.5% spread threshold
            )
            await self.position_monitor.start()
            self.logger.info("Position monitor started - SL/TP enforcement active")

            # Initialize emergency controller for kill switch and emergency stops
            self.emergency_controller = EmergencyController(
                risk_manager=self.risk_manager,
                exchange=self.exchange,
                max_daily_loss_percent=self.config.risk.max_daily_loss_percent / 100,  # Convert from % to decimal
                max_single_position_loss_percent=0.10,  # 10% single position loss limit
                kill_switch_file=None  # Uses default platform-specific path
            )
            self.logger.info("Emergency controller initialized - kill switch active")

            self.logger.info("=" * 50)
            self.logger.info("Trading bot initialized successfully!")
            self.logger.info(f"Symbols: {self.config.trading.symbols}")
            self.logger.info(f"Testnet: {self.config.exchange.testnet}")
            self.logger.info("=" * 50)
        except Exception as e:
            self.logger.error(f"Failed to initialize: {e}")
            raise
    
    async def shutdown(self) -> None:
        """Shutdown and cleanup."""
        self.running = False

        # Stop position monitor first (critical for safety)
        if self.position_monitor:
            try:
                await self.position_monitor.stop()
                self.logger.info("Position monitor stopped")
            except Exception as e:
                self.logger.error(f"Error stopping position monitor: {e}")

        # Stop dashboard
        if self.dashboard:
            try:
                self.dashboard.stop()
            except Exception:
                pass

        try:
            await self.market_data.ws_manager.disconnect_all()
        except Exception:
            pass
        
        try:
            await self.exchange.__aexit__(None, None, None)
        except Exception:
            pass
        
        try:
            await self.timescaledb.close()
            await self.redis.close()
        except Exception:
            pass
        
        self.logger.info("Bot shutdown complete")
    
    async def run(self) -> None:
        """
        Main bot loop.
        
        This is a simplified version. In production, you would:
        1. Connect WebSocket streams
        2. Continuously monitor market data
        3. Generate signals
        4. Execute trades
        """
        self.running = True
        self.logger.info("=" * 50)
        self.logger.info("Trading bot STARTED - Entering main loop")
        self.logger.info("=" * 50)

        # Update dashboard
        if self.dashboard:
            self.dashboard.update_bot_status("🟢 Running - Starting analysis cycle...")
            self.dashboard.heartbeat_time = datetime.now()

        cycle_count = 0
        portfolio_update_counter = 0
        try:
            while self.running:
                cycle_count += 1
                self.logger.info(f"")
                self.logger.info(f"{'='*20} Analysis Cycle #{cycle_count} {'='*20}")

                # Update dashboard heartbeat
                if self.dashboard:
                    self.dashboard.heartbeat_time = datetime.now()

                # Check emergency conditions at the start of each cycle
                if self.emergency_controller:
                    try:
                        account_balance = await self.exchange.get_balance("USDT")
                        emergency_triggered = await self.emergency_controller.check_emergency_triggers(
                            current_balance=account_balance
                        )
                        if emergency_triggered:
                            self.logger.critical("Emergency triggered - stopping trading loop")
                            if self.dashboard:
                                self.dashboard.update_bot_status("🚨 EMERGENCY STOP - Trading halted")
                            self.running = False
                            break

                        # Also check if trading is paused
                        if self.emergency_controller.is_trading_paused():
                            self.logger.warning("Trading paused - skipping cycle")
                            if self.dashboard:
                                self.dashboard.update_bot_status("🟡 Trading paused")
                            await asyncio.sleep(60)
                            continue

                    except Exception as e:
                        self.logger.error(f"Error checking emergency triggers: {e}")

                if self.dashboard:
                    self.dashboard.update_bot_status(f"🟡 Cycle #{cycle_count} - Analyzing symbols...")
                
                # Update portfolio every 5 cycles (5 minutes)
                portfolio_update_counter += 1
                if portfolio_update_counter >= 5:
                    try:
                        portfolio = await self.exchange.get_portfolio_summary()
                        if self.dashboard:
                            self.dashboard.update_wallet_info(portfolio)
                        portfolio_update_counter = 0
                    except Exception as e:
                        self.logger.warning(f"Failed to update portfolio: {e}")
                
                # Main trading loop
                for symbol in self.config.trading.symbols:
                    try:
                        # Update dashboard - analyzing
                        if self.dashboard:
                            self.dashboard.update_bot_status(f"🟡 Analyzing {symbol}...")
                        
                        self.logger.info(f"Starting analysis for {symbol}...")
                        
                        # Get market data
                        df = await self.market_data.get_historical_ohlcv(symbol, interval="1m", hours=24)
                        
                        if df.empty:
                            self.logger.warning(f"No data for {symbol}, skipping")
                            if self.dashboard:
                                self.dashboard.update_bot_status(f"🟡 No data for {symbol}, skipping")
                            await asyncio.sleep(1)  # Brief pause before next symbol
                            continue
                        
                        # Get order book
                        ob_data = await self.market_data.get_order_book_snapshot(symbol, limit=100)
                        from src.analysis.orderbook import OrderBook
                        from src.data.normalization import normalize_orderbook_data
                        ob_normalized = normalize_orderbook_data(ob_data, symbol)
                        order_book = OrderBook(
                            symbol=symbol,
                            bids=[(b[0], b[1]) for b in ob_normalized['bids']],
                            asks=[(a[0], a[1]) for a in ob_normalized['asks']],
                            timestamp=ob_normalized['timestamp']
                        )
                        
                        # Generate signal
                        self.logger.debug(f"Generating signal for {symbol}...")
                        signal = await self.strategy.generate_signal(df, order_book=order_book)
                        self.logger.debug(f"Signal generation complete for {symbol}")
                        
                        # Update dashboard with analysis result
                        # We'll get scores from strategy's last analysis
                        # Strategy stores scores in metadata when signal is generated
                        # For no signal case, we need to modify strategy to expose scores
                        if self.dashboard:
                            max_score = sum(self.config.strategy.weights.values())
                            min_buy_score = self.config.strategy.min_buy_score
                            min_sell_score = self.config.strategy.min_sell_score
                            
                            if signal:
                                buy_score = signal.metadata.get('buy_score', 0.0)
                                sell_score = signal.metadata.get('sell_score', 0.0)
                            else:
                                # No signal - get from strategy's last analysis
                                buy_score = getattr(self.strategy, '_last_buy_score', 0.0)
                                sell_score = getattr(self.strategy, '_last_sell_score', 0.0)
                            
                            self.dashboard.update_analysis_result(
                                symbol=symbol,
                                buy_score=buy_score,
                                sell_score=sell_score,
                                max_score=max_score,
                                min_score=min_buy_score,
                                min_sell_score=min_sell_score,
                                signal_generated=signal is not None
                            )
                            
                            # Update status after analysis
                            if signal:
                                self.dashboard.update_bot_status(f"✅ Analyzed {symbol}: Signal found")
                            else:
                                self.dashboard.update_bot_status(f"✓ Analyzed {symbol}: No signal")
                        
                        if signal:
                            self.logger.info(
                                f"✅ Signal generated: {signal.side} {signal.symbol} @ {signal.entry_price:.2f} "
                                f"(confidence: {signal.confidence:.2f}, score: {signal.metadata.get('buy_score' if signal.side == 'BUY' else 'sell_score', 0):.1f})"
                            )
                            
                            # Update dashboard status
                            if self.dashboard:
                                self.dashboard.update_bot_status(f"🟢 Signal: {signal.side} {symbol}")
                            
                            # Update dashboard with signal
                            if self.dashboard:
                                self.dashboard.add_signal({
                                    'symbol': signal.symbol,
                                    'side': signal.side,
                                    'entry_price': signal.entry_price,
                                    'confidence': signal.confidence,
                                    'timestamp': signal.timestamp
                                })
                            
                            # Get account balance
                            try:
                                account_balance = await self.exchange.get_balance("USDT")
                                self.risk_manager.update_daily_pnl(account_balance)
                                
                                # Update dashboard
                                if self.dashboard:
                                    daily_pnl = self.risk_manager.daily_pnl
                                    daily_pnl_percent = (daily_pnl / self.risk_manager.daily_start_balance * 100) if self.risk_manager.daily_start_balance > 0 else 0.0
                                    self.dashboard.update_account_info(account_balance, daily_pnl, daily_pnl_percent)
                            except Exception as e:
                                self.logger.error(f"Failed to get balance: {e}")
                                account_balance = self.risk_manager.daily_start_balance
                            
                            # Risk validation
                            validation = await self.risk_manager.validate_trade(
                                signal,
                                account_balance,
                                order_book
                            )
                            
                            if validation['approved']:
                                self.logger.info(
                                    f"Trade approved: {signal.symbol} {signal.side} "
                                    f"size={validation['position_size']['position_value_usdt']:.2f} USDT"
                                )
                                
                                # Update dashboard
                                if self.dashboard:
                                    self.dashboard.update_trade_result(True)
                                
                                # Execute trade
                                await self._execute_trade(signal, validation['position_size'], order_book)
                            else:
                                self.logger.warning(f"Trade rejected: {validation['reason']}")
                                
                                # Update dashboard
                                if self.dashboard:
                                    self.dashboard.update_trade_result(False)
                    
                    except Exception as e:
                        self.logger.error(f"Error processing {symbol}: {e}")
                        if self.dashboard:
                            self.dashboard.increment_error()
                            self.dashboard.update_bot_status(f"🔴 Error: {symbol}")
                
                # Update dashboard - cycle complete, waiting for next cycle
                if self.dashboard:
                    symbols_str = ", ".join(self.config.trading.symbols)
                    self.dashboard.update_bot_status(f"🟡 Cycle complete, next in 60s")
                
                # Wait before next iteration
                self.logger.debug("Waiting 60 seconds before next analysis cycle...")
                await asyncio.sleep(60)  # Check every minute
        
        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal")
        finally:
            await self.shutdown()
    
    async def _execute_trade(
        self,
        signal,
        position_size: Dict,
        order_book
    ) -> None:
        """
        Execute a trade.
        
        Args:
            signal: Trading signal
            position_size: Position size information
            order_book: Order book for routing
        """
        try:
            # Determine order type
            from src.analysis.microstructure import MarketMicrostructure
            micro_analyzer = MarketMicrostructure()
            micro = await micro_analyzer.analyze_spread_and_liquidity(order_book)
            
            routing = self.order_router.route_order(
                order_size_usdt=position_size['position_value_usdt'],
                liquidity_quality=micro['liquidity_quality'],
                spread_quality=micro['spread_quality']
            )
            
            if routing['order_type'] == 'reject':
                self.logger.warning(f"Order routing rejected: {routing['reason']}")
                return
            
            # Create order
            order = self.order_lifecycle.create_order(
                symbol=signal.symbol,
                side=signal.side,
                order_type=routing['order_type'],
                quantity=position_size['quantity'],
                price=signal.entry_price if routing['order_type'] == 'limit' else None
            )
            
            # Place order on exchange
            try:
                order_type = 'MARKET' if routing['order_type'] == 'market' else 'LIMIT'
                quote_qty = position_size['position_value_usdt'] if routing['order_type'] == 'market' else None
                quantity = position_size['quantity'] if routing['order_type'] == 'limit' else None
                
                order_response = await self.exchange.place_order(
                    symbol=signal.symbol,
                    side=signal.side,
                    order_type=order_type,
                    quantity=quantity,
                    quote_order_qty=quote_qty,
                    price=signal.entry_price if routing['order_type'] == 'limit' else None
                )
                
                # Update order status
                self.order_lifecycle.update_order_status(
                    order.id,
                    OrderStatus.SUBMITTED,
                    exchange_order_id=str(order_response.get('orderId'))
                )
                
                self.logger.info(f"Order submitted: {order_response.get('orderId')}")
                
                # Monitor order (simplified - in production, use proper monitoring)
                await asyncio.sleep(2)
                
                # Check order status
                order_status = await self.exchange.get_order_status(
                    signal.symbol,
                    order_response['orderId']
                )
                
                if order_status['status'] == 'FILLED':
                    self.order_lifecycle.update_order_status(
                        order.id,
                        OrderStatus.FILLED,
                        filled_quantity=float(order_status.get('executedQty', 0)),
                        avg_fill_price=float(order_status.get('price', signal.entry_price))
                    )
                    
                    # Add position to risk manager
                    position_data = {
                        'id': order.id,
                        'symbol': signal.symbol,
                        'side': signal.side,
                        'entry_price': float(order_status.get('price', signal.entry_price)),
                        'quantity': float(order_status.get('executedQty', 0)),
                        'position_value_usdt': position_size['position_value_usdt'],
                        'stop_loss': signal.stop_loss,
                        'take_profit': signal.take_profit,
                        'unrealized_pnl': 0.0,
                        'unrealized_pnl_percent': 0.0,
                        'opened_at': datetime.now()  # Track when position was opened
                    }
                    self.risk_manager.add_position(position_data)
                    
                    # Update dashboard with positions
                    if self.dashboard:
                        positions = []
                        for pos in self.risk_manager.open_positions:
                            # Calculate unrealized PnL (simplified)
                            current_price = signal.entry_price  # Would need real-time price
                            if pos['side'] == 'BUY':
                                pnl = (current_price - pos['entry_price']) * pos['quantity']
                            else:
                                pnl = (pos['entry_price'] - current_price) * pos['quantity']
                            pnl_percent = (pnl / (pos['entry_price'] * pos['quantity'])) * 100
                            
                            positions.append({
                                **pos,
                                'unrealized_pnl': pnl,
                                'unrealized_pnl_percent': pnl_percent
                            })
                        self.dashboard.update_positions(positions)
                    
                    self.logger.info(
                        f"Order filled: {signal.symbol} {signal.side} "
                        f"{order_status.get('executedQty')} @ {order_status.get('price')}"
                    )
                else:
                    self.order_lifecycle.update_order_status(
                        order.id,
                        OrderStatus.PARTIALLY_FILLED if float(order_status.get('executedQty', 0)) > 0 else OrderStatus.SUBMITTED
                    )
            
            except Exception as e:
                self.logger.error(f"Error executing order: {e}")
                self.order_lifecycle.update_order_status(order.id, OrderStatus.REJECTED)
        
        except Exception as e:
            self.logger.error(f"Error in trade execution: {e}")


async def main():
    """Main entry point."""
    bot = TradingBot()
    
    try:
        await bot.initialize()
        await bot.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
