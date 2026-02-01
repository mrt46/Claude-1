# SUCCESS METRICS (KPIs)

## Overview

This document defines the Key Performance Indicators (KPIs) and success criteria for the Adaptive Multi-Strategy Trading Bot.

## Performance Metrics

### 1. Sharpe Ratio > 2.0

**Definition:**
```
Sharpe Ratio = (Average Return - Risk-Free Rate) / Standard Deviation of Returns
```

**Target:** > 2.0

**Calculation:**
- Daily returns over 90-day period
- Annualized Sharpe = Daily Sharpe × √252
- Risk-free rate: 0% (crypto context)

**Monitoring:**
- Calculate weekly
- Track trend over time
- Alert if drops below 1.5

### 2. Profit Factor > 2.5

**Definition:**
```
Profit Factor = Gross Profit / Gross Loss
```

**Target:** > 2.5

**Interpretation:**
- Profit Factor > 2.5: Very profitable
- Profit Factor 1.5-2.5: Profitable
- Profit Factor < 1.5: Needs improvement

**Monitoring:**
- Calculate monthly
- Track per strategy
- Compare to benchmark

### 3. Win Rate > 60%

**Definition:**
```
Win Rate = Winning Trades / Total Trades
```

**Target:** > 60%

**Note:**
- Win rate alone is not sufficient
- Must combine with profit factor
- High win rate + low profit factor = small wins, big losses

**Monitoring:**
- Calculate weekly
- Track per strategy
- Alert if drops below 50%

## Reliability Metrics

### 4. System Uptime > 99.5%

**Definition:**
```
Uptime = (Total Time - Downtime) / Total Time × 100%
```

**Target:** > 99.5% (≈ 3.6 hours downtime per month)

**Components:**
- Bot running time
- API connectivity
- Database availability
- WebSocket stability

**Monitoring:**
- Track continuously
- Alert on downtime
- Root cause analysis for incidents

### 5. Maximum Drawdown < 15%

**Definition:**
```
Max Drawdown = (Peak Value - Trough Value) / Peak Value
```

**Target:** < 15%

**Interpretation:**
- Max DD < 10%: Excellent
- Max DD 10-15%: Good
- Max DD > 15%: Needs improvement

**Monitoring:**
- Calculate daily
- Track current drawdown
- Alert if exceeds 12%

## Adaptability Metrics

### 6. Strategy Switch Latency < 5 Minutes

**Definition:**
Time from regime change detection to strategy switch completion.

**Target:** < 5 minutes

**Components:**
- Regime detection time
- Strategy selection time
- Position adjustment time

**Monitoring:**
- Track each strategy switch
- Average over 30 days
- Alert if exceeds 10 minutes

### 7. Regime Detection Accuracy > 75%

**Definition:**
```
Accuracy = Correct Regime Predictions / Total Predictions
```

**Target:** > 75%

**Validation:**
- Compare predicted vs actual regime
- Use historical data for validation
- Track accuracy over time

**Monitoring:**
- Calculate weekly
- Track per regime type
- Retrain models if accuracy drops

## Profitability Metrics

### 8. Monthly ROI > 8%

**Definition:**
```
Monthly ROI = (Ending Balance - Starting Balance) / Starting Balance × 100%
```

**Target:** > 8% per month

**Note:**
- Compound monthly: 8% × 12 = 96% annual (theoretical)
- Realistic: 5-10% monthly
- Risk-adjusted returns more important than raw returns

**Monitoring:**
- Calculate monthly
- Track trend
- Compare to benchmark (BTC/ETH)

### 9. Win Rate > 60%

(Already covered above)

## Additional Metrics

### 10. Average Trade Duration

**Target:** Strategy-dependent
- Grid Trading: Hours to days
- Trend Following: Days to weeks
- Mean Reversion: Minutes to hours

### 11. Trade Frequency

**Target:** Strategy-dependent
- Grid Trading: 10-50 trades/day
- Trend Following: 1-5 trades/day
- Mean Reversion: 5-20 trades/day

### 12. Risk-Adjusted Returns

**Metrics:**
- Sortino Ratio (focus on downside risk)
- Calmar Ratio (return / max drawdown)
- Omega Ratio (probability-weighted returns)

**Targets:**
- Sortino Ratio > 2.0
- Calmar Ratio > 1.0
- Omega Ratio > 1.5

## Monitoring Dashboard

### Real-Time Metrics
- Current Sharpe Ratio
- Current Profit Factor
- Current Win Rate
- Current Drawdown
- System Uptime
- Active Strategy
- Recent Trades

### Historical Trends
- Sharpe Ratio over time
- Profit Factor over time
- Win Rate over time
- Drawdown chart
- Equity curve
- Strategy performance comparison

### Alerts
- Sharpe Ratio < 1.5
- Profit Factor < 1.5
- Win Rate < 50%
- Drawdown > 12%
- System downtime
- Strategy underperformance

## Success Criteria Summary

| Metric | Target | Critical Threshold | Alert Threshold |
|--------|--------|-------------------|-----------------|
| Sharpe Ratio | > 2.0 | < 1.0 | < 1.5 |
| Profit Factor | > 2.5 | < 1.0 | < 1.5 |
| Win Rate | > 60% | < 40% | < 50% |
| System Uptime | > 99.5% | < 95% | < 98% |
| Max Drawdown | < 15% | > 25% | > 12% |
| Strategy Switch | < 5 min | > 15 min | > 10 min |
| Regime Accuracy | > 75% | < 50% | < 65% |
| Monthly ROI | > 8% | < 0% | < 4% |

## Review and Optimization

### Weekly Review
- Review all metrics
- Identify underperforming strategies
- Adjust weights if needed

### Monthly Review
- Comprehensive performance analysis
- Strategy optimization
- Model retraining if needed

### Quarterly Review
- Major system optimization
- New strategy evaluation
- Architecture improvements

## Notes

- **Realistic Expectations:** Not all metrics will be met immediately
- **Continuous Improvement:** Focus on trend, not absolute values
- **Risk First:** Safety and risk management take priority over returns
- **Market Dependent:** Performance varies with market conditions
