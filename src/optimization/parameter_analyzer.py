"""
Parameter Performance Analyzer.

Analyzes trade history to identify optimal strategy parameters.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.core.logger import get_logger
from src.data.database import TimescaleDBClient

logger = get_logger(__name__)


class ParameterAnalyzer:
    """
    Analyzes historical trade data to identify optimal parameters.

    Features:
    - Stop-loss distance analysis
    - Take-profit ratio analysis
    - Min score threshold optimization
    - Factor weight correlation
    - Symbol-specific performance
    - Time-based performance patterns
    """

    def __init__(self, database: TimescaleDBClient):
        """
        Initialize parameter analyzer.

        Args:
            database: TimescaleDBClient for trade history access
        """
        self.database = database
        self.logger = logger

    async def analyze_timeframe(
        self,
        hours: int = 24,
        min_trades: int = 5
    ) -> Dict:
        """
        Analyze trades within a timeframe.

        Args:
            hours: Number of hours to look back
            min_trades: Minimum trades required for analysis

        Returns:
            Analysis results dict
        """
        # Get trades from timeframe
        trades = await self.database.get_recent_trades(limit=1000)

        if not trades:
            return {
                'status': 'insufficient_data',
                'message': 'No trades found',
                'trades_count': 0
            }

        # Filter by timeframe
        cutoff_time = datetime.now() - timedelta(hours=hours)
        trades_in_period = [
            t for t in trades
            if isinstance(t.get('exit_time'), datetime) and t['exit_time'] >= cutoff_time
        ]

        if len(trades_in_period) < min_trades:
            return {
                'status': 'insufficient_data',
                'message': f'Only {len(trades_in_period)} trades in last {hours}h (min: {min_trades})',
                'trades_count': len(trades_in_period)
            }

        # Convert to DataFrame for analysis
        df = pd.DataFrame(trades_in_period)

        # Calculate metrics
        results = {
            'status': 'success',
            'timeframe_hours': hours,
            'trades_count': len(trades_in_period),
            'timestamp': datetime.now(),

            # Overall performance
            'overall': self._calculate_overall_metrics(df),

            # Symbol-specific analysis
            'by_symbol': self._analyze_by_symbol(df),

            # Stop-loss analysis
            'stop_loss': self._analyze_stop_loss_performance(df),

            # Closure reason analysis
            'closure_reasons': self._analyze_closure_reasons(df),

            # Hold duration analysis
            'hold_duration': self._analyze_hold_duration(df),

            # Side analysis
            'by_side': self._analyze_by_side(df)
        }

        return results

    def _calculate_overall_metrics(self, df: pd.DataFrame) -> Dict:
        """Calculate overall performance metrics."""
        total_trades = len(df)
        winning_trades = len(df[df['pnl'] > 0])
        losing_trades = len(df[df['pnl'] < 0])
        breakeven_trades = len(df[df['pnl'] == 0])

        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        total_pnl = df['pnl'].sum()
        total_fees = df['total_fees'].sum()
        net_profit = total_pnl - total_fees

        avg_win = df[df['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
        avg_loss = abs(df[df['pnl'] < 0]['pnl'].mean()) if losing_trades > 0 else 0

        profit_factor = (avg_win * winning_trades) / (avg_loss * losing_trades) if losing_trades > 0 and avg_loss > 0 else 0

        # Calculate Sharpe-like ratio (return / volatility)
        pnl_std = df['pnl'].std()
        sharpe_ratio = (df['pnl'].mean() / pnl_std) if pnl_std > 0 else 0

        # Max drawdown
        cumulative_pnl = df['pnl'].cumsum()
        running_max = cumulative_pnl.cummax()
        drawdown = running_max - cumulative_pnl
        max_drawdown = drawdown.max()

        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'breakeven_trades': breakeven_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'total_fees': total_fees,
            'net_profit': net_profit,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'avg_hold_minutes': df['hold_duration_seconds'].mean() / 60 if 'hold_duration_seconds' in df else 0
        }

    def _analyze_by_symbol(self, df: pd.DataFrame) -> Dict:
        """Analyze performance by trading symbol."""
        if 'symbol' not in df.columns:
            return {}

        results = {}
        for symbol in df['symbol'].unique():
            symbol_df = df[df['symbol'] == symbol]

            total = len(symbol_df)
            winning = len(symbol_df[symbol_df['pnl'] > 0])
            win_rate = (winning / total * 100) if total > 0 else 0

            results[symbol] = {
                'total_trades': total,
                'winning_trades': winning,
                'losing_trades': len(symbol_df[symbol_df['pnl'] < 0]),
                'win_rate': win_rate,
                'total_pnl': symbol_df['pnl'].sum(),
                'avg_pnl': symbol_df['pnl'].mean(),
                'total_fees': symbol_df['total_fees'].sum(),
                'best_trade': symbol_df['pnl'].max(),
                'worst_trade': symbol_df['pnl'].min()
            }

        # Sort by total_pnl
        results = dict(sorted(results.items(), key=lambda x: x[1]['total_pnl'], reverse=True))

        return results

    def _analyze_stop_loss_performance(self, df: pd.DataFrame) -> Dict:
        """Analyze stop-loss effectiveness."""
        if 'closure_reason' not in df.columns:
            return {}

        # Stop-loss hits
        sl_hits = df[df['closure_reason'].str.contains('STOP_LOSS', na=False, case=False)]
        tp_hits = df[df['closure_reason'].str.contains('TAKE_PROFIT', na=False, case=False)]

        total = len(df)
        sl_count = len(sl_hits)
        tp_count = len(tp_hits)

        sl_rate = (sl_count / total * 100) if total > 0 else 0
        tp_rate = (tp_count / total * 100) if total > 0 else 0

        # Analyze if SL was too tight (price reversed after hitting SL)
        # This would require order book data, so we'll use PnL as proxy
        sl_avg_loss = sl_hits['pnl'].mean() if len(sl_hits) > 0 else 0

        return {
            'stop_loss_hits': sl_count,
            'stop_loss_rate': sl_rate,
            'take_profit_hits': tp_count,
            'take_profit_rate': tp_rate,
            'sl_avg_loss': sl_avg_loss,
            'tp_avg_profit': tp_hits['pnl'].mean() if len(tp_hits) > 0 else 0,
            'sl_to_tp_ratio': sl_count / tp_count if tp_count > 0 else 0
        }

    def _analyze_closure_reasons(self, df: pd.DataFrame) -> Dict:
        """Analyze distribution of closure reasons."""
        if 'closure_reason' not in df.columns:
            return {}

        reason_counts = df['closure_reason'].value_counts().to_dict()
        total = len(df)

        reason_percentages = {
            reason: (count / total * 100) for reason, count in reason_counts.items()
        }

        # Average PnL by closure reason
        reason_pnl = df.groupby('closure_reason')['pnl'].agg(['mean', 'sum', 'count']).to_dict('index')

        return {
            'counts': reason_counts,
            'percentages': reason_percentages,
            'pnl_by_reason': reason_pnl
        }

    def _analyze_hold_duration(self, df: pd.DataFrame) -> Dict:
        """Analyze relationship between hold duration and profitability."""
        if 'hold_duration_seconds' not in df.columns:
            return {}

        df['hold_minutes'] = df['hold_duration_seconds'] / 60

        # Categorize by duration
        bins = [0, 30, 60, 120, 240, float('inf')]
        labels = ['0-30m', '30-60m', '1-2h', '2-4h', '4h+']
        df['duration_bucket'] = pd.cut(df['hold_minutes'], bins=bins, labels=labels)

        duration_analysis = df.groupby('duration_bucket', observed=True).agg({
            'pnl': ['count', 'mean', 'sum'],
            'pnl_percent': 'mean'
        }).to_dict()

        # Optimal hold time (duration with best avg PnL)
        optimal_bucket = df.groupby('duration_bucket', observed=True)['pnl'].mean().idxmax()

        return {
            'avg_hold_minutes': df['hold_minutes'].mean(),
            'median_hold_minutes': df['hold_minutes'].median(),
            'min_hold_minutes': df['hold_minutes'].min(),
            'max_hold_minutes': df['hold_minutes'].max(),
            'by_duration': duration_analysis,
            'optimal_duration_bucket': optimal_bucket
        }

    def _analyze_by_side(self, df: pd.DataFrame) -> Dict:
        """Analyze performance by trade side (BUY vs SELL)."""
        if 'side' not in df.columns:
            return {}

        results = {}
        for side in df['side'].unique():
            side_df = df[df['side'] == side]

            total = len(side_df)
            winning = len(side_df[side_df['pnl'] > 0])
            win_rate = (winning / total * 100) if total > 0 else 0

            results[side] = {
                'total_trades': total,
                'winning_trades': winning,
                'losing_trades': len(side_df[side_df['pnl'] < 0]),
                'win_rate': win_rate,
                'total_pnl': side_df['pnl'].sum(),
                'avg_pnl': side_df['pnl'].mean(),
                'avg_pnl_percent': side_df['pnl_percent'].mean()
            }

        return results

    def identify_parameter_issues(self, analysis: Dict) -> List[Dict]:
        """
        Identify potential parameter issues from analysis.

        Args:
            analysis: Analysis results from analyze_timeframe()

        Returns:
            List of issues with severity and description
        """
        issues = []

        if analysis['status'] != 'success':
            return issues

        overall = analysis['overall']
        stop_loss = analysis.get('stop_loss', {})

        # Issue 1: Low win rate
        if overall['win_rate'] < 50:
            issues.append({
                'severity': 'high',
                'category': 'win_rate',
                'description': f"Win rate is low ({overall['win_rate']:.1f}%). Consider adjusting min_score threshold.",
                'current_value': overall['win_rate'],
                'expected_value': 55.0
            })

        # Issue 2: High stop-loss rate (more SL hits than TP)
        if stop_loss.get('sl_to_tp_ratio', 0) > 1.5:
            issues.append({
                'severity': 'high',
                'category': 'stop_loss',
                'description': f"Stop-loss hit rate is high ({stop_loss['sl_to_tp_ratio']:.2f}x more than TP). Stop-loss may be too tight.",
                'current_value': stop_loss['sl_to_tp_ratio'],
                'expected_value': 1.0
            })

        # Issue 3: Negative net profit
        if overall['net_profit'] < 0:
            issues.append({
                'severity': 'critical',
                'category': 'profitability',
                'description': f"Net profit is negative (${overall['net_profit']:.2f}). Strategy needs adjustment.",
                'current_value': overall['net_profit'],
                'expected_value': 0
            })

        # Issue 4: Poor profit factor
        if overall['profit_factor'] < 1.5:
            issues.append({
                'severity': 'medium',
                'category': 'profit_factor',
                'description': f"Profit factor is low ({overall['profit_factor']:.2f}). Avg win not sufficient compared to avg loss.",
                'current_value': overall['profit_factor'],
                'expected_value': 2.0
            })

        # Issue 5: High fees relative to PnL
        if overall['total_pnl'] > 0:
            fee_ratio = overall['total_fees'] / overall['total_pnl']
            if fee_ratio > 0.3:  # Fees eating 30%+ of profits
                issues.append({
                    'severity': 'medium',
                    'category': 'fees',
                    'description': f"Fees are {fee_ratio*100:.1f}% of total PnL. Consider reducing trade frequency or using BNB for fees.",
                    'current_value': fee_ratio,
                    'expected_value': 0.15
                })

        # Issue 6: Symbol-specific underperformance
        by_symbol = analysis.get('by_symbol', {})
        for symbol, stats in by_symbol.items():
            if stats['total_trades'] >= 3 and stats['win_rate'] < 30:
                issues.append({
                    'severity': 'medium',
                    'category': 'symbol_performance',
                    'description': f"{symbol} has very low win rate ({stats['win_rate']:.1f}%). Consider excluding or adjusting parameters for this symbol.",
                    'current_value': stats['win_rate'],
                    'expected_value': 50.0,
                    'symbol': symbol
                })

        return issues
