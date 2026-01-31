"""
Recommendation Engine for Parameter Optimization.

Generates actionable recommendations based on parameter analysis.
"""

from typing import Dict, List, Optional

from src.core.logger import get_logger

logger = get_logger(__name__)


class RecommendationEngine:
    """
    Generates parameter optimization recommendations.

    Based on historical performance analysis, suggests:
    - Stop-loss distance adjustments
    - Take-profit ratio changes
    - Min score threshold optimization
    - Factor weight rebalancing
    - Symbol inclusion/exclusion
    """

    def __init__(self):
        """Initialize recommendation engine."""
        self.logger = logger

    def generate_recommendations(
        self,
        analysis: Dict,
        issues: List[Dict],
        current_config: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Generate optimization recommendations.

        Args:
            analysis: Analysis results from ParameterAnalyzer
            issues: Issues identified by ParameterAnalyzer
            current_config: Current strategy configuration

        Returns:
            List of recommendations with priority, description, and suggested changes
        """
        if analysis['status'] != 'success':
            return []

        recommendations = []

        # Process each identified issue
        for issue in issues:
            category = issue['category']

            if category == 'stop_loss':
                recommendations.extend(
                    self._recommend_stop_loss_adjustment(analysis, issue)
                )
            elif category == 'win_rate':
                recommendations.extend(
                    self._recommend_score_threshold_adjustment(analysis, issue)
                )
            elif category == 'profit_factor':
                recommendations.extend(
                    self._recommend_risk_reward_adjustment(analysis, issue)
                )
            elif category == 'fees':
                recommendations.extend(
                    self._recommend_fee_optimization(analysis, issue)
                )
            elif category == 'symbol_performance':
                recommendations.extend(
                    self._recommend_symbol_adjustment(analysis, issue)
                )

        # Additional opportunistic recommendations
        recommendations.extend(
            self._recommend_from_positive_insights(analysis)
        )

        # Sort by priority (critical > high > medium > low)
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        recommendations.sort(key=lambda x: priority_order.get(x['priority'], 4))

        return recommendations

    def _recommend_stop_loss_adjustment(
        self,
        analysis: Dict,
        issue: Dict
    ) -> List[Dict]:
        """Recommend stop-loss distance adjustments."""
        recommendations = []

        stop_loss = analysis.get('stop_loss', {})
        sl_rate = stop_loss.get('stop_loss_rate', 0)
        tp_rate = stop_loss.get('take_profit_rate', 0)

        if sl_rate > tp_rate * 1.5:
            # Too many stop-loss hits relative to take-profit
            recommendations.append({
                'priority': 'high',
                'category': 'stop_loss_distance',
                'title': 'Widen Stop-Loss Distance',
                'description': f'Stop-loss hit rate ({sl_rate:.1f}%) is {sl_rate/tp_rate:.1f}x higher than take-profit ({tp_rate:.1f}%). This suggests stop-loss is too tight.',
                'action': 'Increase stop-loss distance from 2% to 2.5-3%',
                'expected_impact': f'+15-20% win rate improvement',
                'suggested_config': {
                    'stop_loss_percent': 2.5  # Current is likely 2.0
                },
                'rationale': 'Wider stop-loss gives trades more room to breathe, reducing premature exits on volatility spikes.'
            })

        return recommendations

    def _recommend_score_threshold_adjustment(
        self,
        analysis: Dict,
        issue: Dict
    ) -> List[Dict]:
        """Recommend min_score threshold adjustments."""
        recommendations = []

        overall = analysis['overall']
        win_rate = overall['win_rate']

        if win_rate < 50:
            # Low win rate - increase threshold for better quality signals
            recommendations.append({
                'priority': 'high',
                'category': 'min_score',
                'title': 'Increase Min Score Threshold',
                'description': f'Win rate is {win_rate:.1f}%, below target of 55%. Tighten entry requirements.',
                'action': 'Increase min_score from 7.0 to 7.5 or 8.0',
                'expected_impact': '-20% trade frequency, +10-15% win rate',
                'suggested_config': {
                    'min_score': 7.5,
                    'min_buy_score': 7.5,
                    'min_sell_score': 7.5
                },
                'rationale': 'Higher threshold filters out weaker signals, improving trade quality at the cost of frequency.'
            })
        elif win_rate > 70 and overall['total_trades'] < 10:
            # High win rate but few trades - decrease threshold for more opportunities
            recommendations.append({
                'priority': 'medium',
                'category': 'min_score',
                'title': 'Lower Min Score Threshold',
                'description': f'Win rate is excellent ({win_rate:.1f}%) but only {overall["total_trades"]} trades. Increase frequency.',
                'action': 'Decrease min_score from 7.0 to 6.5',
                'expected_impact': '+30-50% trade frequency, minimal win rate impact',
                'suggested_config': {
                    'min_score': 6.5,
                    'min_buy_score': 6.5,
                    'min_sell_score': 6.5
                },
                'rationale': 'Current threshold is too conservative. Lower it to capture more opportunities without sacrificing quality.'
            })

        return recommendations

    def _recommend_risk_reward_adjustment(
        self,
        analysis: Dict,
        issue: Dict
    ) -> List[Dict]:
        """Recommend risk/reward ratio adjustments."""
        recommendations = []

        overall = analysis['overall']
        profit_factor = overall['profit_factor']
        avg_win = overall['avg_win']
        avg_loss = overall['avg_loss']

        if profit_factor < 1.5 and avg_win > 0 and avg_loss > 0:
            # Poor profit factor - need better R/R
            rr_ratio = avg_win / avg_loss

            if rr_ratio < 2.0:
                recommendations.append({
                    'priority': 'high',
                    'category': 'risk_reward',
                    'title': 'Improve Risk/Reward Ratio',
                    'description': f'Current R/R ratio is {rr_ratio:.2f}:1 (avg win ${avg_win:.2f} / avg loss ${avg_loss:.2f}). Target is 2:1.',
                    'action': 'Adjust take-profit targets to aim for 2.5:1 or 3:1 R/R',
                    'expected_impact': '+0.5-1.0 profit factor improvement',
                    'suggested_config': {
                        'take_profit_ratio': 2.5  # Current is likely 2.0
                    },
                    'rationale': 'Higher take-profit targets improve profit factor, allowing strategy to be profitable with lower win rate.'
                })

        return recommendations

    def _recommend_fee_optimization(
        self,
        analysis: Dict,
        issue: Dict
    ) -> List[Dict]:
        """Recommend fee optimization strategies."""
        recommendations = []

        overall = analysis['overall']
        total_fees = overall['total_fees']
        total_pnl = overall['total_pnl']

        if total_pnl > 0:
            fee_ratio = total_fees / total_pnl

            if fee_ratio > 0.2:
                recommendations.append({
                    'priority': 'medium',
                    'category': 'fees',
                    'title': 'Enable BNB Fee Payment',
                    'description': f'Fees are {fee_ratio*100:.1f}% of total PnL (${total_fees:.2f}). Using BNB reduces fees by 25%.',
                    'action': 'Ensure BNB balance is sufficient and BNB fee payment is enabled',
                    'expected_impact': f'-25% fee reduction (~${total_fees * 0.25:.2f} saved)',
                    'suggested_config': {
                        'use_bnb_for_fees': True,
                        'min_bnb_balance': 0.1
                    },
                    'rationale': 'Binance gives 25% fee discount when using BNB to pay trading fees. Essential for high-frequency strategies.'
                })

                # Also suggest reducing trade frequency if fees are extreme
                if fee_ratio > 0.4:
                    recommendations.append({
                        'priority': 'high',
                        'category': 'trade_frequency',
                        'title': 'Reduce Trade Frequency',
                        'description': f'Fees are eating {fee_ratio*100:.1f}% of profits. Strategy may be over-trading.',
                        'action': 'Increase min_score threshold to reduce trade frequency',
                        'expected_impact': f'-30% trade frequency, -{fee_ratio*30:.1f}% fees',
                        'suggested_config': {
                            'min_score': 7.5
                        },
                        'rationale': 'Each trade incurs 0.2% fees (0.1% entry + 0.1% exit). Fewer, higher-quality trades improve net profit.'
                    })

        return recommendations

    def _recommend_symbol_adjustment(
        self,
        analysis: Dict,
        issue: Dict
    ) -> List[Dict]:
        """Recommend symbol inclusion/exclusion."""
        recommendations = []

        symbol = issue.get('symbol')
        if not symbol:
            return recommendations

        by_symbol = analysis.get('by_symbol', {})
        symbol_stats = by_symbol.get(symbol, {})

        win_rate = symbol_stats.get('win_rate', 0)
        total_trades = symbol_stats.get('total_trades', 0)
        total_pnl = symbol_stats.get('total_pnl', 0)

        if total_trades >= 5 and (win_rate < 35 or total_pnl < -50):
            recommendations.append({
                'priority': 'high',
                'category': 'symbol_exclusion',
                'title': f'Consider Excluding {symbol}',
                'description': f'{symbol} has poor performance: {win_rate:.1f}% win rate, ${total_pnl:.2f} total PnL over {total_trades} trades.',
                'action': f'Remove {symbol} from trading pairs or adjust strategy parameters specifically for {symbol}',
                'expected_impact': f'Avoid ${abs(total_pnl):.2f} in losses',
                'suggested_config': {
                    'excluded_symbols': [symbol]
                },
                'rationale': f'{symbol} may not be suitable for current strategy. Some coins have different volatility/liquidity characteristics.'
            })

        return recommendations

    def _recommend_from_positive_insights(self, analysis: Dict) -> List[Dict]:
        """Generate recommendations from positive performance insights."""
        recommendations = []

        by_symbol = analysis.get('by_symbol', {})
        overall = analysis['overall']

        # Find top-performing symbols
        if by_symbol:
            sorted_symbols = sorted(
                by_symbol.items(),
                key=lambda x: x[1].get('total_pnl', 0),
                reverse=True
            )

            top_symbol = sorted_symbols[0]
            symbol_name = top_symbol[0]
            symbol_stats = top_symbol[1]

            if (
                symbol_stats.get('total_trades', 0) >= 5
                and symbol_stats.get('win_rate', 0) > 70
                and symbol_stats.get('total_pnl', 0) > 100
            ):
                recommendations.append({
                    'priority': 'low',
                    'category': 'symbol_focus',
                    'title': f'Increase {symbol_name} Exposure',
                    'description': f'{symbol_name} performing excellently: {symbol_stats["win_rate"]:.1f}% win rate, ${symbol_stats["total_pnl"]:.2f} profit.',
                    'action': f'Consider increasing position size for {symbol_name} or focusing more on this pair',
                    'expected_impact': f'+{symbol_stats["total_pnl"] * 0.5:.2f} potential additional profit',
                    'suggested_config': {
                        'symbol_position_size_multipliers': {
                            symbol_name: 1.5
                        }
                    },
                    'rationale': f'{symbol_name} shows strong compatibility with current strategy. Capitalize on this edge.'
                })

        # Hold duration insights
        hold_duration = analysis.get('hold_duration', {})
        optimal_bucket = hold_duration.get('optimal_duration_bucket')

        if optimal_bucket:
            recommendations.append({
                'priority': 'low',
                'category': 'hold_duration',
                'title': f'Optimal Hold Duration: {optimal_bucket}',
                'description': f'Trades held for {optimal_bucket} show best average PnL.',
                'action': 'Consider adding hold duration targets or trailing stops to capture this pattern',
                'expected_impact': 'Optimization of exit timing',
                'suggested_config': {
                    'optimal_hold_duration_minutes': optimal_bucket
                },
                'rationale': 'Understanding optimal hold time helps set better take-profit targets and exit strategies.'
            })

        return recommendations

    def format_recommendations_for_display(
        self,
        recommendations: List[Dict],
        max_display: int = 5
    ) -> str:
        """
        Format recommendations as readable text.

        Args:
            recommendations: List of recommendation dicts
            max_display: Maximum recommendations to display

        Returns:
            Formatted string
        """
        if not recommendations:
            return "✅ No optimization recommendations. Performance is satisfactory."

        output = []
        output.append(f"🎯 TOP {min(len(recommendations), max_display)} RECOMMENDATIONS:\n")

        priority_emoji = {
            'critical': '🔴',
            'high': '🟠',
            'medium': '🟡',
            'low': '🟢'
        }

        for i, rec in enumerate(recommendations[:max_display], 1):
            emoji = priority_emoji.get(rec['priority'], '⚪')
            output.append(f"{i}. {emoji} {rec['title']} ({rec['priority'].upper()})")
            output.append(f"   {rec['description']}")
            output.append(f"   → Action: {rec['action']}")
            output.append(f"   → Impact: {rec['expected_impact']}")
            output.append("")

        return "\n".join(output)
