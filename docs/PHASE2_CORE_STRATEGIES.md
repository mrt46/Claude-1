# PHASE 2: CORE STRATEGIES IMPLEMENTATION (Week 3-4)

## Overview

Phase 2 implements three core trading strategies that will form the foundation of the adaptive multi-strategy system: Grid Trading, Trend Following, and Mean Reversion.

## Objectives

1. Implement Grid Trading Strategy with volatility-adaptive spacing
2. Implement Trend Following Strategy with multi-timeframe confirmation
3. Implement Mean Reversion Strategy with statistical confirmation
4. Ensure all strategies inherit from BaseStrategy interface

## Strategies

### 1. Grid Trading Strategy

#### Purpose
Capture profits in ranging markets by placing buy/sell orders at regular intervals.

#### Key Features

**Dynamic Grid Calculation:**
- Grid spacing based on ATR (Average True Range)
  - High volatility: Wider spacing (2x ATR)
  - Low volatility: Tighter spacing (1x ATR)
- Grid levels: 5-10 levels above/below current price
- Grid rebalancing when price moves >50% of grid range

**Grid Rebalancing Logic:**
- Monitor price position within grid
- When price approaches grid edge, shift grid center
- Maintain equal number of buy/sell orders
- Close profitable orders automatically

**Profit-Taking and Grid Reset:**
- Take profit: 1-2% per grid level
- Stop loss: 3-5% below lowest buy order
- Grid reset: When trend breaks (ADX > 25)
- Emergency close: On high volatility spike (>3x ATR)

**Implementation:**
```python
class GridTradingStrategy(BaseStrategy):
    def __init__(self, grid_levels: int = 10, profit_target: float = 0.02):
        self.grid_levels = grid_levels
        self.profit_target = profit_target
        self.grid_orders = []
    
    async def generate_signal(self, df, market_regime, **kwargs):
        # Calculate grid spacing based on ATR
        # Place grid orders
        # Monitor and rebalance
        pass
    
    def calculate_fitness_score(self, market_regime):
        # High score in: Low volatility, range-bound markets
        # Low score in: Strong trends, high volatility
        pass
```

**Ideal Market Conditions:**
- Volatility: Low to Medium
- Trend: Neutral (ADX < 20)
- Phase: Accumulation or Distribution
- Volume: Stable

### 2. Trend Following Strategy

#### Purpose
Capture profits in trending markets by following price momentum.

#### Key Features

**Multi-Timeframe EMA System:**
- Fast EMA: 20 periods
- Medium EMA: 50 periods
- Long EMA: 200 periods
- Timeframes: 1h, 4h, 1d (higher timeframe confirmation)

**ADX Confirmation:**
- Entry only when ADX > 25 (strong trend)
- Exit when ADX < 20 (trend weakening)
- ADX slope confirmation (trend strengthening)

**Dynamic Stop-Loss Trailing:**
- Initial stop: 2% below entry (long) or above (short)
- Trail stop using ATR: Stop = Entry ± (2x ATR)
- Move stop to breakeven after 1% profit
- Trailing stop: Lock in 50% of max profit

**Momentum Filters:**
- MACD: Bullish crossover for long, bearish for short
- RSI: Confirm trend (RSI > 50 for uptrend, < 50 for downtrend)
- Volume: Increasing volume confirms trend
- Confluence: All indicators must agree

**Implementation:**
```python
class TrendFollowingStrategy(BaseStrategy):
    def __init__(self, ema_fast: int = 20, ema_slow: int = 50, adx_threshold: float = 25):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.adx_threshold = adx_threshold
    
    async def generate_signal(self, df, market_regime, **kwargs):
        # Calculate EMAs
        # Check ADX
        # Confirm with MACD, RSI
        # Generate signal
        pass
    
    def calculate_fitness_score(self, market_regime):
        # High score in: Strong trends (ADX > 25)
        # Low score in: Range-bound, low volatility
        pass
```

**Ideal Market Conditions:**
- Trend: Strong (ADX > 25)
- Direction: Clear bullish or bearish
- Phase: Markup or Markdown
- Volume: Increasing

### 3. Mean Reversion Strategy

#### Purpose
Profit from price returning to mean after extreme moves.

#### Key Features

**Bollinger Band Squeeze Detection:**
- Detect when BB width < 20th percentile (squeeze)
- Wait for expansion breakout
- Enter on reversal back to mean
- Confirm with volume spike

**RSI Extremes:**
- Oversold: RSI < 30 (buy signal)
- Overbought: RSI > 70 (sell signal)
- Divergence: Price makes new low/high but RSI doesn't
- RSI confirmation: Wait for RSI to cross back above 30 (buy) or below 70 (sell)

**Standard Deviation from Mean:**
- Calculate 20-period moving average
- Calculate 2σ and 3σ levels
- Enter when price > 2σ (sell) or < -2σ (buy)
- Strong signal at 3σ levels

**Volume Confirmation:**
- Require volume spike on reversal
- Volume > 1.5x average for confirmation
- Reversal candle with high volume

**Implementation:**
```python
class MeanReversionStrategy(BaseStrategy):
    def __init__(self, bb_period: int = 20, rsi_period: int = 14, std_multiplier: float = 2.0):
        self.bb_period = bb_period
        self.rsi_period = rsi_period
        self.std_multiplier = std_multiplier
    
    async def generate_signal(self, df, market_regime, **kwargs):
        # Check BB squeeze
        # Check RSI extremes
        # Check std deviation
        # Confirm with volume
        pass
    
    def calculate_fitness_score(self, market_regime):
        # High score in: Range-bound, mean-reverting markets
        # Low score in: Strong trends
        pass
```

**Ideal Market Conditions:**
- Volatility: Medium (BB squeeze)
- Trend: Weak (ADX < 20)
- Phase: Accumulation or Distribution
- Price: At extremes (2σ+ from mean)

## Implementation Tasks

### Week 3
- [ ] Implement Grid Trading Strategy
  - [ ] Dynamic grid calculation
  - [ ] Grid rebalancing logic
  - [ ] Profit-taking mechanism
- [ ] Unit tests for Grid Strategy

### Week 4
- [ ] Implement Trend Following Strategy
  - [ ] Multi-timeframe EMA system
  - [ ] ADX confirmation
  - [ ] Dynamic stop-loss trailing
- [ ] Implement Mean Reversion Strategy
  - [ ] Bollinger Band squeeze detection
  - [ ] RSI extremes
  - [ ] Standard deviation levels
- [ ] Integration tests for all strategies
- [ ] Strategy performance comparison

## Success Criteria

- ✅ All three strategies implemented
- ✅ Strategies inherit from BaseStrategy
- ✅ Fitness scores calculated correctly
- ✅ Strategies generate signals in appropriate market conditions
- ✅ Unit and integration tests passing
- ✅ Strategy performance tracked

## Risk Considerations

- **Grid Strategy:** Risk of trend break (use stop loss)
- **Trend Strategy:** Risk of false breakouts (use ADX confirmation)
- **Mean Reversion:** Risk of continued trend (use volume confirmation)

## Next Phase

Once Phase 2 is complete, proceed to [Phase 3: Intelligent Strategy Selection](./PHASE3_STRATEGY_SELECTION.md)
