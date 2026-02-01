# PHASE 3: INTELLIGENT STRATEGY SELECTION (Week 5-6)

## Overview

Phase 3 implements the intelligent strategy selection system that automatically chooses the best strategy based on current market conditions and performance history.

## Objectives

1. Implement Strategy Selector Agent (StrategyManager)
2. Create market condition → strategy mapping rules
3. Implement multi-strategy fitness scoring system
4. Add confidence-based capital allocation
5. Implement strategy transition smoothing
6. Enhance risk management layer

## Components

### 1. Strategy Selector Agent (StrategyManager)

#### Purpose
Intelligently select and allocate capital to the best-performing strategy for current market conditions.

#### Key Features

**Market Condition → Strategy Mapping:**
```python
STRATEGY_MAPPING = {
    'strong_trend_high_vol': TrendFollowingStrategy,
    'strong_trend_low_vol': TrendFollowingStrategy,
    'weak_trend_range': GridTradingStrategy,
    'no_trend_squeeze': MeanReversionStrategy,
    'high_volatility': GridTradingStrategy,  # Wider grids
    'low_volatility': MeanReversionStrategy,  # Tighter ranges
}
```

**Multi-Strategy Fitness Scoring:**
- Each strategy calculates fitness score (0.0 - 1.0)
- Factors:
  - Market regime match (40%)
  - Recent performance (30%)
  - Risk-adjusted returns (20%)
  - Current drawdown (10%)
- Select strategy with highest fitness score
- Minimum fitness threshold: 0.6

**Confidence-Based Capital Allocation:**
- High confidence (fitness > 0.8): Allocate 100% of available capital
- Medium confidence (0.6-0.8): Allocate 50-75% of capital
- Low confidence (< 0.6): No allocation, wait for better conditions
- Multiple strategies: Split capital based on fitness scores

**Strategy Transition Smoothing:**
- Avoid whipsaws: Don't switch strategies too frequently
- Minimum hold time: 1 hour (for 1m timeframe)
- Transition buffer: Only switch if new strategy fitness > current + 0.15
- Gradual transition: Reduce old strategy, increase new strategy over 5-10 minutes

**Implementation:**
```python
class StrategyManager:
    def __init__(self, strategies: List[BaseStrategy]):
        self.strategies = strategies
        self.current_strategy = None
        self.strategy_history = []
    
    async def select_strategy(self, market_regime: MarketRegime) -> BaseStrategy:
        # Calculate fitness scores for all strategies
        # Apply transition smoothing
        # Select best strategy
        # Allocate capital
        pass
    
    def calculate_capital_allocation(self, strategy: BaseStrategy, fitness: float) -> float:
        # Confidence-based allocation
        pass
```

### 2. Risk Management Layer

#### Purpose
Enhanced risk management for multi-strategy system.

#### Key Features

**Per-Strategy Position Limits:**
- Maximum position size per strategy
- Maximum total exposure across all strategies
- Correlation-aware limits (avoid overexposure to similar strategies)

**Correlation-Aware Exposure Control:**
- Calculate correlation between strategies
- If two strategies are highly correlated (>0.7), reduce combined exposure
- Diversification bonus: Reward uncorrelated strategy combinations

**Dynamic Position Sizing (Kelly Criterion):**
- Calculate optimal position size using Kelly Criterion
- Kelly % = (Win Rate × Avg Win - Loss Rate × Avg Loss) / Avg Win
- Apply fractional Kelly (0.25x or 0.5x for safety)
- Adjust based on strategy performance

**Maximum Drawdown Circuit Breakers:**
- Per-strategy drawdown limit: 10%
- Total portfolio drawdown limit: 15%
- When limit reached: Pause strategy, reduce position sizes
- Recovery mode: Gradually increase after drawdown recovery

**Implementation:**
```python
class MultiStrategyRiskManager:
    def __init__(self, max_total_exposure: float = 0.8):
        self.max_total_exposure = max_total_exposure
        self.strategy_exposures = {}
        self.drawdown_tracker = {}
    
    def validate_trade(self, strategy: BaseStrategy, signal: Signal, 
                      current_positions: List) -> Dict:
        # Check per-strategy limits
        # Check correlation
        # Check drawdown
        # Calculate position size (Kelly)
        pass
    
    def calculate_kelly_position_size(self, strategy: BaseStrategy) -> float:
        # Get strategy performance metrics
        # Calculate Kelly %
        # Apply fractional Kelly
        pass
```

## Implementation Tasks

### Week 5
- [ ] Implement StrategyManager
  - [ ] Market condition mapping
  - [ ] Fitness scoring system
  - [ ] Strategy selection logic
- [ ] Implement capital allocation
- [ ] Unit tests

### Week 6
- [ ] Implement MultiStrategyRiskManager
  - [ ] Per-strategy limits
  - [ ] Correlation calculation
  - [ ] Kelly Criterion position sizing
  - [ ] Drawdown circuit breakers
- [ ] Strategy transition smoothing
- [ ] Integration tests
- [ ] Performance testing

## Success Criteria

- ✅ Strategy selection accuracy > 75%
- ✅ Strategy switch latency < 5 minutes
- ✅ Capital allocation optimized
- ✅ Risk limits enforced
- ✅ No whipsaw transitions
- ✅ All tests passing

## Risk Considerations

- **Strategy Switching:** Avoid frequent switches (transaction costs)
- **Capital Allocation:** Don't over-allocate to single strategy
- **Correlation:** Monitor strategy correlations
- **Drawdown:** Strict circuit breakers

## Next Phase

Once Phase 3 is complete, proceed to [Phase 4: Performance Tracking & Analytics](./PHASE4_PERFORMANCE_TRACKING.md)
