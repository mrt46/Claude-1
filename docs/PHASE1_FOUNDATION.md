# PHASE 1: FOUNDATION & MARKET INTELLIGENCE (Week 1-2)

## Overview

Phase 1 establishes the foundation for adaptive strategy selection by implementing market regime detection and creating the strategy interface framework.

## Objectives

1. Detect current market conditions (trend, volatility, volume, phase)
2. Create abstract strategy base classes with standardized interfaces
3. Implement performance tracking hooks for strategy evaluation

## Components

### 1. Market Regime Detection System

#### 1.1 Trend Detector
**Purpose:** Identify market trend direction and strength

**Components:**
- **ADX (Average Directional Index)**
  - Calculate ADX(14) for trend strength
  - ADX > 25 = Strong trend
  - ADX < 20 = Weak trend/range-bound
  
- **EMA Crossovers**
  - Fast EMA (20) vs Slow EMA (50)
  - Fast EMA (50) vs Long EMA (200)
  - Golden Cross / Death Cross detection
  - Crossover confirmation (wait for 2-3 candles)
  
- **Slope Analysis**
  - Calculate EMA slope (degrees or percentage)
  - Trend strength: Steep > Moderate > Flat
  - Multi-timeframe slope comparison

**Output:**
```python
TrendRegime = {
    'direction': 'bullish' | 'bearish' | 'neutral',
    'strength': 'strong' | 'moderate' | 'weak',
    'adx': float,
    'ema_cross': 'bullish' | 'bearish' | 'none',
    'slope': float
}
```

#### 1.2 Volatility Analyzer
**Purpose:** Measure market volatility to adjust strategy parameters

**Components:**
- **ATR (Average True Range)**
  - ATR(14) calculation
  - ATR percentage of price
  - ATR trend (increasing/decreasing)
  
- **Bollinger Band Width**
  - BB width = (Upper Band - Lower Band) / Middle Band
  - Squeeze detection (width < 20th percentile)
  - Expansion detection (width > 80th percentile)
  
- **Historical Volatility**
  - 20-day rolling standard deviation
  - Volatility percentile (vs 100-day history)
  - Volatility regime: High / Medium / Low

**Output:**
```python
VolatilityRegime = {
    'level': 'high' | 'medium' | 'low',
    'atr': float,
    'atr_percent': float,
    'bb_squeeze': bool,
    'historical_vol': float,
    'vol_percentile': float
}
```

#### 1.3 Volume Profiler
**Purpose:** Analyze volume patterns for market participation

**Components:**
- **Volume Trend**
  - Volume moving average (20, 50 periods)
  - Volume trend direction (increasing/decreasing)
  - Volume vs price divergence detection
  
- **Volume Spikes**
  - Detect volume > 2x average
  - Volume spike confirmation (sustained vs one-off)
  - Volume spike location (breakout vs reversal)
  
- **Relative Volume Strength**
  - Current volume / Average volume ratio
  - Volume strength percentile
  - Institutional vs retail volume patterns

**Output:**
```python
VolumeRegime = {
    'trend': 'increasing' | 'decreasing' | 'stable',
    'strength': 'high' | 'medium' | 'low',
    'spike_detected': bool,
    'relative_volume': float,
    'volume_percentile': float
}
```

#### 1.4 Market Phase Detector (Wyckoff Cycle)
**Purpose:** Identify market cycle phase for strategy selection

**Components:**
- **Accumulation Phase**
  - Price consolidation after downtrend
  - Decreasing volume
  - Support level formation
  
- **Markup Phase**
  - Strong uptrend
  - Increasing volume
  - Higher highs and higher lows
  
- **Distribution Phase**
  - Price consolidation after uptrend
  - Decreasing volume
  - Resistance level formation
  
- **Markdown Phase**
  - Strong downtrend
  - Increasing volume
  - Lower highs and lower lows

**Output:**
```python
MarketPhase = {
    'phase': 'accumulation' | 'markup' | 'distribution' | 'markdown',
    'confidence': float,  # 0.0 - 1.0
    'transition_risk': float  # Risk of phase change
}
```

### 2. Strategy Interface & Base Classes

#### 2.1 Abstract Strategy Base
**Purpose:** Standardized interface for all trading strategies

**Interface:**
```python
class BaseStrategy(ABC):
    @abstractmethod
    async def generate_signal(self, df: pd.DataFrame, **kwargs) -> Optional[Signal]:
        """Generate trading signal"""
        pass
    
    @abstractmethod
    def calculate_fitness_score(self, market_regime: MarketRegime) -> float:
        """Calculate how well this strategy fits current market conditions"""
        pass
    
    @abstractmethod
    def get_required_regime(self) -> MarketRegime:
        """Return ideal market conditions for this strategy"""
        pass
```

**Key Methods:**
- `generate_signal()`: Core signal generation
- `calculate_fitness_score()`: Regime matching score (0.0 - 1.0)
- `get_required_regime()`: Ideal market conditions
- `update_performance()`: Track strategy performance
- `get_performance_metrics()`: Return win rate, profit factor, etc.

#### 2.2 Standardized Signal Generation
**Purpose:** Consistent signal format across all strategies

**Signal Structure:**
```python
@dataclass
class StrategySignal:
    strategy_name: str
    symbol: str
    side: str  # 'BUY' | 'SELL'
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float  # 0.0 - 1.0
    fitness_score: float  # How well strategy fits current regime
    timestamp: datetime
    metadata: dict
```

#### 2.3 Performance Tracking Hooks
**Purpose:** Track strategy performance for optimization

**Metrics to Track:**
- Win Rate (wins / total trades)
- Profit Factor (gross profit / gross loss)
- Sharpe Ratio (risk-adjusted returns)
- Maximum Drawdown
- Average Win / Average Loss
- Trade Frequency
- Regime-specific performance

**Implementation:**
- Database table: `strategy_performance`
- Real-time updates after each trade
- Rolling windows (7-day, 30-day, 90-day)
- Regime-specific performance mapping

## Implementation Tasks

### Week 1
- [ ] Implement Trend Detector (ADX, EMA, Slope)
- [ ] Implement Volatility Analyzer (ATR, BB, Historical Vol)
- [ ] Create MarketRegime data class
- [ ] Unit tests for regime detection

### Week 2
- [ ] Implement Volume Profiler
- [ ] Implement Market Phase Detector (Wyckoff)
- [ ] Create BaseStrategy abstract class
- [ ] Create StrategySignal data class
- [ ] Implement performance tracking hooks
- [ ] Integration tests

## Success Criteria

- ✅ Market regime detection accuracy > 75%
- ✅ Regime detection latency < 50ms
- ✅ Strategy base class interface complete
- ✅ Performance tracking functional
- ✅ All unit tests passing

## Dependencies

- Existing volume profile analysis
- Existing order book analysis
- TimescaleDB for performance storage
- Redis for regime caching

## Next Phase

Once Phase 1 is complete, proceed to [Phase 2: Core Strategies Implementation](./PHASE2_CORE_STRATEGIES.md)
