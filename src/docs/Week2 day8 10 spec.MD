# 📋 WEEK 2 - DAY 8-10 DETAILED SPECIFICATION
## Backtesting Framework (Historical Testing & Strategy Validation)

**Duration:** 3 days  
**Priority:** HIGH ⚠️  
**Dependencies:** Week 1 complete (all core systems working)

---

## 🎯 OBJECTIVES

1. **Backtesting Engine:** Test strategies on historical data
2. **Historical Data Downloader:** Get OHLCV & trades from Binance
3. **Fill Simulator:** Realistic order execution simulation
4. **Performance Metrics:** Comprehensive strategy evaluation
5. **Report Generator:** Beautiful HTML reports with charts

**Why Important:**
- Validate strategies before risking real money
- Optimize parameters on historical data
- Understand strategy behavior in different market conditions
- Build confidence in trading system

---

## 📂 FILES TO CREATE

```
src/backtest/
├── engine.py                    (NEW - 400 lines)
├── data_downloader.py           (NEW - 250 lines)
├── fill_simulator.py            (NEW - 200 lines)
├── performance_metrics.py       (NEW - 300 lines)
├── report_generator.py          (NEW - 250 lines)
└── __init__.py                  (NEW)

data/
└── historical/                  (NEW - data storage)
    ├── BTCUSDT_1h.csv
    ├── ETHUSDT_1h.csv
    └── ...

scripts/
├── download_data.py             (NEW - 150 lines)
├── run_backtest.py              (NEW - 200 lines)
└── optimize_strategy.py         (NEW - 300 lines)

tests/unit/
├── test_backtest_engine.py      (NEW - 200 lines)
├── test_fill_simulator.py       (NEW - 150 lines)
└── test_performance_metrics.py  (NEW - 150 lines)
```

---

## 📝 DETAILED SPECIFICATIONS

---

## 1. BACKTESTING ENGINE

### File: `src/backtest/engine.py`

#### Class: `BacktestEngine`

**Purpose:** Main backtesting engine that replays historical data and simulates trading.

**Constructor:**
```python
class BacktestEngine:
    """
    Backtesting engine for strategy validation.
    
    Replays historical market data and simulates trading
    to evaluate strategy performance.
    """
    
    def __init__(
        self,
        strategy: BaseStrategy,
        symbol: str,
        start_date: str,
        end_date: str,
        initial_capital: float = 10000.0,
        commission: float = 0.001,  # 0.1%
        slippage_percent: float = 0.001  # 0.1%
    ):
        """
        Initialize backtest engine.
        
        Args:
            strategy: Strategy to test (must inherit BaseStrategy)
            symbol: Trading pair (e.g., 'BTCUSDT')
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            initial_capital: Starting capital in USDT
            commission: Trading fee rate (default: 0.001 = 0.1%)
            slippage_percent: Slippage rate (default: 0.001 = 0.1%)
        """
        self.strategy = strategy
        self.symbol = symbol
        self.start_date = pd.Timestamp(start_date)
        self.end_date = pd.Timestamp(end_date)
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage_percent = slippage_percent
        
        # Backtest state
        self.capital = initial_capital
        self.position: Optional[BacktestPosition] = None
        self.trades: List[BacktestTrade] = []
        self.equity_curve: List[EquityPoint] = []
        
        # Components
        self.fill_simulator = FillSimulator(
            commission=commission,
            slippage_percent=slippage_percent
        )
        
        logger.info(
            f"BacktestEngine initialized: "
            f"{symbol} from {start_date} to {end_date}, "
            f"capital=${initial_capital:.2f}"
        )
```

**Main Methods:**

#### 1.1 `run()`
```python
async def run(self) -> BacktestResult:
    """
    Run backtest.
    
    Process:
    1. Load historical data
    2. For each candle:
       a. Update strategy indicators
       b. Generate signal
       c. Execute trades
       d. Update positions
       e. Record equity
    3. Calculate performance metrics
    4. Generate report
    
    Returns:
        BacktestResult with trades, metrics, equity curve
    """
    logger.info(f"Starting backtest for {self.symbol}")
    
    # Load data
    df = await self._load_historical_data()
    
    if df.empty:
        raise ValueError("No historical data available")
    
    logger.info(f"Loaded {len(df)} candles from {df.index[0]} to {df.index[-1]}")
    
    # Initialize strategy
    self.strategy.initialize(df)
    
    # Main backtest loop
    for i in range(len(df)):
        # Current candle
        current_time = df.index[i]
        current_data = df.iloc[:i+1]  # Data up to current candle
        
        # Check if position needs to close (SL/TP hit)
        if self.position:
            await self._check_position_exit(
                df.iloc[i],
                current_time
            )
        
        # Generate signal (only if no position)
        if not self.position:
            signal = await self.strategy.generate_signal(current_data)
            
            if signal:
                await self._execute_signal(
                    signal,
                    df.iloc[i],
                    current_time
                )
        
        # Record equity point
        equity = self._calculate_current_equity(df.iloc[i])
        self.equity_curve.append(
            EquityPoint(
                timestamp=current_time,
                equity=equity,
                capital=self.capital,
                position_value=self._get_position_value(df.iloc[i])
            )
        )
    
    # Close any open position at end
    if self.position:
        await self._close_position(
            df.iloc[-1],
            df.index[-1],
            reason='BACKTEST_END'
        )
    
    # Calculate performance metrics
    metrics = self._calculate_metrics()
    
    # Create result
    result = BacktestResult(
        symbol=self.symbol,
        start_date=self.start_date,
        end_date=self.end_date,
        initial_capital=self.initial_capital,
        final_capital=self.capital,
        trades=self.trades,
        equity_curve=self.equity_curve,
        metrics=metrics,
        strategy_name=self.strategy.name
    )
    
    logger.info(
        f"Backtest complete: {len(self.trades)} trades, "
        f"final capital=${self.capital:.2f}, "
        f"return={metrics['total_return_percent']:.2f}%"
    )
    
    return result
```

#### 1.2 `_load_historical_data()`
```python
async def _load_historical_data(self) -> pd.DataFrame:
    """
    Load historical OHLCV data.
    
    Tries to load from cache first, downloads if not available.
    
    Returns:
        DataFrame with OHLCV data
    """
    cache_path = f"data/historical/{self.symbol}_1h.csv"
    
    # Try cache first
    if os.path.exists(cache_path):
        logger.debug(f"Loading data from cache: {cache_path}")
        df = pd.read_csv(cache_path, index_col='timestamp', parse_dates=True)
        
        # Filter to date range
        df = df[(df.index >= self.start_date) & (df.index <= self.end_date)]
        
        if not df.empty:
            return df
    
    # Download fresh data
    logger.info(f"Downloading historical data for {self.symbol}")
    downloader = HistoricalDataDownloader()
    
    df = await downloader.download_ohlcv(
        symbol=self.symbol,
        interval='1h',
        start_date=self.start_date.strftime('%Y-%m-%d'),
        end_date=self.end_date.strftime('%Y-%m-%d')
    )
    
    # Save to cache
    os.makedirs('data/historical', exist_ok=True)
    df.to_csv(cache_path)
    logger.info(f"Data cached to {cache_path}")
    
    return df
```

#### 1.3 `_execute_signal(signal, candle, timestamp)`
```python
async def _execute_signal(
    self,
    signal: Signal,
    candle: pd.Series,
    timestamp: pd.Timestamp
) -> None:
    """
    Execute trading signal.
    
    Args:
        signal: Trading signal
        candle: Current OHLCV candle
        timestamp: Current time
    """
    logger.debug(f"Executing signal: {signal.side} at {candle['close']:.2f}")
    
    # Calculate position size
    current_price = candle['close']
    
    # Risk-based sizing (2% risk)
    risk_amount = self.capital * 0.02
    risk_per_unit = abs(current_price - signal.stop_loss)
    
    if risk_per_unit == 0:
        logger.warning("Stop loss equals entry price, skipping trade")
        return
    
    quantity = risk_amount / risk_per_unit
    
    # Check if enough capital
    position_value = quantity * current_price
    if position_value > self.capital * 0.95:  # Max 95% of capital
        quantity = (self.capital * 0.95) / current_price
        logger.warning(f"Position size reduced to fit capital: {quantity:.5f}")
    
    # Simulate order fill
    fill_result = self.fill_simulator.simulate_fill(
        price=current_price,
        quantity=quantity,
        side=signal.side,
        candle=candle
    )
    
    # Deduct from capital
    cost = fill_result.filled_price * fill_result.filled_quantity + fill_result.commission
    self.capital -= cost
    
    # Create position
    self.position = BacktestPosition(
        symbol=self.symbol,
        side=signal.side,
        entry_price=fill_result.filled_price,
        quantity=fill_result.filled_quantity,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        opened_at=timestamp,
        entry_commission=fill_result.commission
    )
    
    logger.info(
        f"Position opened: {signal.side} {fill_result.filled_quantity:.5f} @ "
        f"{fill_result.filled_price:.2f}, capital=${self.capital:.2f}"
    )
```

#### 1.4 `_check_position_exit(candle, timestamp)`
```python
async def _check_position_exit(
    self,
    candle: pd.Series,
    timestamp: pd.Timestamp
) -> None:
    """
    Check if position should exit (SL/TP hit).
    
    Args:
        candle: Current OHLCV candle
        timestamp: Current time
    """
    if not self.position:
        return
    
    # Check stop-loss
    if self.position.side == 'BUY':
        # Long position
        if candle['low'] <= self.position.stop_loss:
            # Stop-loss hit
            await self._close_position(
                candle,
                timestamp,
                reason='STOP_LOSS',
                exit_price=self.position.stop_loss
            )
            return
        
        # Check take-profit
        if self.position.take_profit and candle['high'] >= self.position.take_profit:
            # Take-profit hit
            await self._close_position(
                candle,
                timestamp,
                reason='TAKE_PROFIT',
                exit_price=self.position.take_profit
            )
            return
    
    else:  # SELL (short)
        # Short position
        if candle['high'] >= self.position.stop_loss:
            # Stop-loss hit
            await self._close_position(
                candle,
                timestamp,
                reason='STOP_LOSS',
                exit_price=self.position.stop_loss
            )
            return
        
        if self.position.take_profit and candle['low'] <= self.position.take_profit:
            # Take-profit hit
            await self._close_position(
                candle,
                timestamp,
                reason='TAKE_PROFIT',
                exit_price=self.position.take_profit
            )
            return
```

#### 1.5 `_close_position(candle, timestamp, reason, exit_price)`
```python
async def _close_position(
    self,
    candle: pd.Series,
    timestamp: pd.Timestamp,
    reason: str,
    exit_price: Optional[float] = None
) -> None:
    """
    Close position.
    
    Args:
        candle: Current candle
        timestamp: Current time
        reason: Closure reason
        exit_price: Override exit price (for SL/TP)
    """
    if not self.position:
        return
    
    # Determine exit price
    if exit_price is None:
        exit_price = candle['close']
    
    # Simulate exit fill
    fill_result = self.fill_simulator.simulate_fill(
        price=exit_price,
        quantity=self.position.quantity,
        side='SELL' if self.position.side == 'BUY' else 'BUY',
        candle=candle
    )
    
    # Add to capital
    proceeds = fill_result.filled_price * fill_result.filled_quantity - fill_result.commission
    self.capital += proceeds
    
    # Calculate PnL
    if self.position.side == 'BUY':
        # Long
        gross_pnl = (fill_result.filled_price - self.position.entry_price) * self.position.quantity
    else:
        # Short
        gross_pnl = (self.position.entry_price - fill_result.filled_price) * self.position.quantity
    
    net_pnl = gross_pnl - self.position.entry_commission - fill_result.commission
    
    # Create trade record
    hold_duration = timestamp - self.position.opened_at
    
    trade = BacktestTrade(
        symbol=self.symbol,
        side=self.position.side,
        entry_price=self.position.entry_price,
        exit_price=fill_result.filled_price,
        quantity=self.position.quantity,
        pnl=net_pnl,
        pnl_percent=(net_pnl / (self.position.entry_price * self.position.quantity)) * 100,
        opened_at=self.position.opened_at,
        closed_at=timestamp,
        hold_duration=hold_duration,
        closure_reason=reason,
        entry_commission=self.position.entry_commission,
        exit_commission=fill_result.commission
    )
    
    self.trades.append(trade)
    
    logger.info(
        f"Position closed ({reason}): "
        f"PnL=${net_pnl:+.2f} ({trade.pnl_percent:+.2f}%), "
        f"hold={hold_duration}, capital=${self.capital:.2f}"
    )
    
    # Clear position
    self.position = None
```

---

## 2. HISTORICAL DATA DOWNLOADER

### File: `src/backtest/data_downloader.py`

#### Class: `HistoricalDataDownloader`

**Purpose:** Download historical OHLCV and trades data from Binance.

```python
class HistoricalDataDownloader:
    """
    Download historical data from Binance.
    
    Downloads OHLCV candles and trades for backtesting.
    """
    
    def __init__(self, testnet: bool = False):
        """
        Initialize data downloader.
        
        Args:
            testnet: Use testnet API (default: False)
        """
        self.testnet = testnet
        self.client = Client("", "")  # No auth needed for public data
        
        if testnet:
            self.client.API_URL = 'https://testnet.binance.vision/api'
        
        logger.info("HistoricalDataDownloader initialized")
    
    async def download_ohlcv(
        self,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Download OHLCV candles.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            interval: Candle interval ('1m', '5m', '1h', '1d')
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            DataFrame with columns: open, high, low, close, volume
        """
        logger.info(
            f"Downloading {symbol} {interval} data "
            f"from {start_date} to {end_date}"
        )
        
        # Convert dates to timestamps
        start_ts = int(pd.Timestamp(start_date).timestamp() * 1000)
        end_ts = int(pd.Timestamp(end_date).timestamp() * 1000)
        
        # Binance limit: 1000 candles per request
        # Need to make multiple requests for large date ranges
        
        all_candles = []
        current_ts = start_ts
        
        while current_ts < end_ts:
            try:
                # Get candles
                candles = await self.client.get_klines(
                    symbol=symbol,
                    interval=interval,
                    startTime=current_ts,
                    endTime=end_ts,
                    limit=1000
                )
                
                if not candles:
                    break
                
                all_candles.extend(candles)
                
                # Update current timestamp to last candle
                current_ts = candles[-1][0] + 1  # Next ms after last candle
                
                logger.debug(
                    f"Downloaded {len(candles)} candles, "
                    f"total: {len(all_candles)}"
                )
                
                # Rate limiting
                await asyncio.sleep(0.1)
            
            except Exception as e:
                logger.error(f"Error downloading data: {e}")
                break
        
        # Convert to DataFrame
        df = pd.DataFrame(all_candles, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades',
            'taker_buy_base', 'taker_buy_quote', 'ignore'
        ])
        
        # Select and convert columns
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        # Convert to numeric
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        
        logger.info(
            f"Downloaded {len(df)} candles: "
            f"{df.index[0]} to {df.index[-1]}"
        )
        
        return df
```

---

## 3. FILL SIMULATOR

### File: `src/backtest/fill_simulator.py`

```python
@dataclass
class FillResult:
    """Order fill simulation result"""
    filled_price: float
    filled_quantity: float
    commission: float
    slippage: float


class FillSimulator:
    """
    Simulate order fills in backtest.
    
    Models realistic execution with:
    - Commission
    - Slippage
    - Partial fills (optional)
    """
    
    def __init__(
        self,
        commission: float = 0.001,
        slippage_percent: float = 0.001
    ):
        """
        Initialize fill simulator.
        
        Args:
            commission: Commission rate (default: 0.001 = 0.1%)
            slippage_percent: Slippage rate (default: 0.001 = 0.1%)
        """
        self.commission = commission
        self.slippage_percent = slippage_percent
        
        logger.info(
            f"FillSimulator: "
            f"commission={commission*100}%, "
            f"slippage={slippage_percent*100}%"
        )
    
    def simulate_fill(
        self,
        price: float,
        quantity: float,
        side: str,
        candle: pd.Series
    ) -> FillResult:
        """
        Simulate market order fill.
        
        Args:
            price: Order price
            quantity: Order quantity
            side: 'BUY' or 'SELL'
            candle: Current OHLCV candle
            
        Returns:
            FillResult with filled price, quantity, commission, slippage
        """
        # Slippage simulation
        if side == 'BUY':
            # Buying: price increases
            slippage_amount = price * self.slippage_percent
            filled_price = price + slippage_amount
            
            # Cap at candle high
            filled_price = min(filled_price, candle['high'])
        
        else:  # SELL
            # Selling: price decreases
            slippage_amount = price * self.slippage_percent
            filled_price = price - slippage_amount
            
            # Cap at candle low
            filled_price = max(filled_price, candle['low'])
        
        # Full fill (simplification)
        filled_quantity = quantity
        
        # Commission
        trade_value = filled_price * filled_quantity
        commission = trade_value * self.commission
        
        return FillResult(
            filled_price=filled_price,
            filled_quantity=filled_quantity,
            commission=commission,
            slippage=abs(filled_price - price)
        )
```

---

## 4. PERFORMANCE METRICS

### File: `src/backtest/performance_metrics.py`

```python
class PerformanceMetrics:
    """
    Calculate comprehensive performance metrics.
    """
    
    @staticmethod
    def calculate_all_metrics(
        trades: List[BacktestTrade],
        equity_curve: List[EquityPoint],
        initial_capital: float
    ) -> Dict[str, float]:
        """
        Calculate all performance metrics.
        
        Returns dict with 20+ metrics.
        """
        if not trades:
            return {'error': 'No trades'}
        
        # Basic metrics
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl < 0]
        
        num_wins = len(winning_trades)
        num_losses = len(losing_trades)
        
        win_rate = (num_wins / total_trades) * 100 if total_trades > 0 else 0
        
        # PnL metrics
        total_pnl = sum(t.pnl for t in trades)
        avg_pnl = total_pnl / total_trades
        
        avg_win = sum(t.pnl for t in winning_trades) / num_wins if num_wins > 0 else 0
        avg_loss = sum(t.pnl for t in losing_trades) / num_losses if num_losses > 0 else 0
        
        max_win = max((t.pnl for t in trades), default=0)
        max_loss = min((t.pnl for t in trades), default=0)
        
        # Return metrics
        final_capital = equity_curve[-1].equity
        total_return = final_capital - initial_capital
        total_return_percent = (total_return / initial_capital) * 100
        
        # Drawdown
        peak = initial_capital
        max_drawdown = 0
        
        for point in equity_curve:
            if point.equity > peak:
                peak = point.equity
            
            drawdown = (peak - point.equity) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        max_drawdown_percent = max_drawdown * 100
        
        # Sharpe Ratio (simplified)
        returns = [point.equity / equity_curve[i-1].equity - 1 
                   for i, point in enumerate(equity_curve) if i > 0]
        
        if returns:
            avg_return = np.mean(returns)
            std_return = np.std(returns)
            sharpe_ratio = (avg_return / std_return) * np.sqrt(252) if std_return > 0 else 0
        else:
            sharpe_ratio = 0
        
        # Profit Factor
        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Expectancy
        expectancy = (win_rate/100 * avg_win) + ((1 - win_rate/100) * avg_loss)
        
        return {
            'total_trades': total_trades,
            'winning_trades': num_wins,
            'losing_trades': num_losses,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'total_return_percent': total_return_percent,
            'avg_pnl': avg_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'max_win': max_win,
            'max_loss': max_loss,
            'max_drawdown_percent': max_drawdown_percent,
            'sharpe_ratio': sharpe_ratio,
            'profit_factor': profit_factor,
            'expectancy': expectancy,
            'initial_capital': initial_capital,
            'final_capital': final_capital
        }
```

---

## 🚀 CURSOR PROMPTS

### Prompt 1: Create Backtest Engine

```
Create src/backtest/engine.py implementing BacktestEngine class.

Read specification in WEEK2_DAY8-10_SPEC.md (Backtesting Engine section).

Requirements:
1. Implement run() method - main backtest loop
2. Load historical data (from cache or download)
3. For each candle: check exits, generate signals, execute trades
4. Track equity curve
5. Calculate performance metrics
6. Return BacktestResult

Critical logic:
- Check SL/TP on EVERY candle (use candle high/low)
- Only generate signals when NO position open
- Simulate realistic fills (with slippage, commission)
- Track capital correctly (deduct on entry, add on exit)

This allows testing strategies on historical data before live trading!
```

### Prompt 2: Create Data Downloader

```
Create src/backtest/data_downloader.py implementing HistoricalDataDownloader.

Read specification in WEEK2_DAY8-10_SPEC.md (Data Downloader section).

Requirements:
1. download_ohlcv() - Download candles from Binance
2. Handle pagination (1000 candles per request limit)
3. Convert to pandas DataFrame
4. Cache data locally

Use Binance public API (no authentication needed).
Handle rate limits with sleep between requests.

Example usage:
```python
downloader = HistoricalDataDownloader()
df = await downloader.download_ohlcv(
    'BTCUSDT', '1h', '2024-01-01', '2024-12-31'
)
print(f"Downloaded {len(df)} candles")
```

This enables backtesting on any date range!
```

### Prompt 3: Create Fill Simulator

```
Create src/backtest/fill_simulator.py implementing FillSimulator.

Read specification in WEEK2_DAY8-10_SPEC.md (Fill Simulator section).

Requirements:
1. simulate_fill() - Simulate market order execution
2. Apply slippage (buy: price up, sell: price down)
3. Apply commission (0.1% default)
4. Return FillResult with filled price, quantity, commission

Realistic simulation:
- BUY order: filled_price = order_price * (1 + slippage)
- SELL order: filled_price = order_price * (1 - slippage)
- Cap filled price within candle range (high/low)

This ensures backtest is realistic (not too optimistic)!
```

### Prompt 4: Create Performance Metrics

```
Create src/backtest/performance_metrics.py implementing PerformanceMetrics.

Read specification in WEEK2_DAY8-10_SPEC.md (Performance Metrics section).

Implement calculate_all_metrics() returning dict with:
- Total trades, win rate
- Total PnL, average PnL
- Average win, average loss
- Max win, max loss
- Max drawdown (%)
- Sharpe ratio
- Profit factor
- Expectancy

All metrics are essential for evaluating strategy quality!
```

### Prompt 5: Create Scripts & Tests

```
Create helper scripts and tests:

1. scripts/download_data.py
   - CLI script to download historical data
   - Save to data/historical/

2. scripts/run_backtest.py
   - CLI script to run backtest
   - Print results

3. tests/unit/test_backtest_engine.py
   - Test backtest loop
   - Test position tracking
   - Test PnL calculation

All scripts should be runnable from command line!
```

---

## ✅ ACCEPTANCE CRITERIA

Day 8-10 complete when:

```
Code:
□ BacktestEngine created (400+ lines)
□ HistoricalDataDownloader created (250+ lines)
□ FillSimulator created (200+ lines)
□ PerformanceMetrics created (300+ lines)
□ Helper scripts created
□ All type hints & docstrings present

Tests:
□ test_backtest_engine.py (10+ tests)
□ test_fill_simulator.py (8+ tests)
□ test_performance_metrics.py (8+ tests)
□ All tests passing

Validation:
□ Can download data for BTCUSDT
□ Can run backtest on 6 months data
□ Backtest completes in < 1 minute
□ Metrics calculated correctly
□ Results are reproducible

Manual Test:
□ python scripts/download_data.py BTCUSDT 2024-01-01 2024-06-30
□ python scripts/run_backtest.py BTCUSDT 2024-01-01 2024-06-30
□ Verify positive expectancy on good strategy
```

---

## 📊 ESTIMATED TIME

- Backtest Engine: 6-8 hours
- Data Downloader: 3-4 hours
- Fill Simulator: 2-3 hours
- Performance Metrics: 3-4 hours
- Scripts & CLI: 2-3 hours
- Unit Tests: 4-5 hours
- Integration Testing: 3-4 hours

**Total: 23-31 hours (3 days)**

---

**DAY 8-10 SPEC COMPLETE! 🎉**

Next: Day 11-12 (Performance Optimization)...