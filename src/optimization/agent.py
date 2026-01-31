"""
Optimization Agent.

Monitors bot performance, analyzes trade history, and generates
optimization recommendations every 24 hours.
"""

import asyncio
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.core.logger import get_logger
from src.data.database import TimescaleDBClient
from src.optimization.parameter_analyzer import ParameterAnalyzer
from src.optimization.recommendation_engine import RecommendationEngine

logger = get_logger(__name__)


class OptimizationAgent:
    """
    Autonomous optimization agent.

    Features:
    - Runs analysis every 24 hours (or on-demand)
    - Monitors trade performance and parameters
    - Identifies issues and opportunities
    - Generates actionable recommendations
    - Stores recommendations for dashboard display
    """

    def __init__(
        self,
        database: TimescaleDBClient,
        analysis_interval_hours: int = 24,
        min_trades_for_analysis: int = 10
    ):
        """
        Initialize optimization agent.

        Args:
            database: TimescaleDBClient for trade history access
            analysis_interval_hours: Hours between automatic analyses
            min_trades_for_analysis: Minimum trades required for analysis
        """
        self.database = database
        self.analysis_interval_hours = analysis_interval_hours
        self.min_trades_for_analysis = min_trades_for_analysis

        # Components
        self.analyzer = ParameterAnalyzer(database)
        self.recommender = RecommendationEngine()

        # State
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_analysis_time: Optional[datetime] = None
        self.last_analysis_result: Optional[Dict] = None
        self.last_recommendations: List[Dict] = []
        self.last_issues: List[Dict] = []

        self.logger = logger

    def start(self) -> None:
        """Start optimization agent in background thread."""
        if self.running:
            self.logger.warning("Optimization agent already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self.logger.info(
            f"Optimization agent started (analysis every {self.analysis_interval_hours}h)"
        )

    def stop(self) -> None:
        """Stop optimization agent."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.logger.info("Optimization agent stopped")

    def _run_loop(self) -> None:
        """Main agent loop (runs in background thread)."""
        # Wait 5 minutes before first check to avoid startup conflicts
        self.logger.info("Optimization agent waiting 5 minutes before first analysis check...")
        threading.Event().wait(300)  # 5 minutes

        while self.running:
            try:
                # Check if it's time for analysis
                should_analyze = False

                if self.last_analysis_time is None:
                    # First analysis - wait 1 hour for initial data
                    if self._get_system_uptime_hours() >= 1:
                        should_analyze = True
                else:
                    # Regular interval
                    time_since_last = datetime.now() - self.last_analysis_time
                    if time_since_last >= timedelta(hours=self.analysis_interval_hours):
                        should_analyze = True

                if should_analyze:
                    self.logger.info("Starting scheduled optimization analysis...")
                    try:
                        asyncio.run(self.run_analysis())
                    except Exception as analysis_error:
                        self.logger.error(f"Analysis failed: {analysis_error}")
                        # Continue running, will try again later

                # Sleep for 1 hour before checking again
                threading.Event().wait(3600)

            except Exception as e:
                self.logger.error(f"Optimization agent error: {e}", exc_info=True)
                threading.Event().wait(3600)  # Wait 1 hour on error

    def _get_system_uptime_hours(self) -> float:
        """Get approximate system uptime (stub for now)."""
        # In production, this would track actual bot start time
        # For now, return a reasonable default
        return 24.0

    async def run_analysis(
        self,
        hours: Optional[int] = None,
        min_trades: Optional[int] = None
    ) -> Dict:
        """
        Run optimization analysis.

        Args:
            hours: Hours to analyze (default: 24)
            min_trades: Minimum trades required (default: from config)

        Returns:
            Analysis summary with recommendations
        """
        hours = hours or self.analysis_interval_hours
        min_trades = min_trades or self.min_trades_for_analysis

        self.logger.info(f"Running optimization analysis (last {hours}h, min {min_trades} trades)...")

        try:
            # Step 1: Analyze trade history
            analysis = await self.analyzer.analyze_timeframe(
                hours=hours,
                min_trades=min_trades
            )

            if analysis['status'] != 'success':
                self.logger.warning(f"Analysis incomplete: {analysis.get('message', 'Unknown reason')}")
                return {
                    'status': 'incomplete',
                    'message': analysis.get('message'),
                    'timestamp': datetime.now()
                }

            # Step 2: Identify issues
            issues = self.analyzer.identify_parameter_issues(analysis)
            self.logger.info(f"Identified {len(issues)} potential issues")

            # Step 3: Generate recommendations
            recommendations = self.recommender.generate_recommendations(
                analysis=analysis,
                issues=issues,
                current_config=None  # Could pass current config from main.py
            )
            self.logger.info(f"Generated {len(recommendations)} recommendations")

            # Step 4: Store results
            self.last_analysis_time = datetime.now()
            self.last_analysis_result = analysis
            self.last_recommendations = recommendations
            self.last_issues = issues

            # Log summary
            self._log_analysis_summary(analysis, issues, recommendations)

            return {
                'status': 'success',
                'timestamp': datetime.now(),
                'analysis': analysis,
                'issues': issues,
                'recommendations': recommendations
            }

        except Exception as e:
            self.logger.error(f"Analysis failed: {e}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e),
                'timestamp': datetime.now()
            }

    def _log_analysis_summary(
        self,
        analysis: Dict,
        issues: List[Dict],
        recommendations: List[Dict]
    ) -> None:
        """Log analysis summary to console."""
        overall = analysis.get('overall', {})

        self.logger.info("=" * 60)
        self.logger.info("OPTIMIZATION ANALYSIS SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Timeframe: {analysis['timeframe_hours']}h")
        self.logger.info(f"Total Trades: {overall.get('total_trades', 0)}")
        self.logger.info(f"Win Rate: {overall.get('win_rate', 0):.1f}%")
        self.logger.info(f"Total PnL: ${overall.get('total_pnl', 0):.2f}")
        self.logger.info(f"Net Profit: ${overall.get('net_profit', 0):.2f}")
        self.logger.info(f"Profit Factor: {overall.get('profit_factor', 0):.2f}")
        self.logger.info(f"Sharpe Ratio: {overall.get('sharpe_ratio', 0):.2f}")
        self.logger.info("-" * 60)
        self.logger.info(f"Issues Found: {len(issues)}")
        for issue in issues[:3]:  # Show top 3
            self.logger.info(f"  [{issue['severity'].upper()}] {issue['description']}")
        self.logger.info("-" * 60)
        self.logger.info(f"Recommendations: {len(recommendations)}")
        for rec in recommendations[:3]:  # Show top 3
            self.logger.info(f"  [{rec['priority'].upper()}] {rec['title']}")
        self.logger.info("=" * 60)

    def get_latest_recommendations(self, max_count: int = 5) -> List[Dict]:
        """
        Get latest recommendations.

        Args:
            max_count: Maximum recommendations to return

        Returns:
            List of recommendations
        """
        return self.last_recommendations[:max_count]

    def get_latest_issues(self, max_count: int = 5) -> List[Dict]:
        """
        Get latest issues.

        Args:
            max_count: Maximum issues to return

        Returns:
            List of issues
        """
        return self.last_issues[:max_count]

    def get_analysis_summary(self) -> Optional[Dict]:
        """
        Get summary of last analysis.

        Returns:
            Analysis summary dict or None if no analysis yet
        """
        if not self.last_analysis_result:
            return None

        overall = self.last_analysis_result.get('overall', {})

        return {
            'timestamp': self.last_analysis_time,
            'timeframe_hours': self.last_analysis_result.get('timeframe_hours', 24),
            'total_trades': overall.get('total_trades', 0),
            'win_rate': overall.get('win_rate', 0),
            'total_pnl': overall.get('total_pnl', 0),
            'net_profit': overall.get('net_profit', 0),
            'profit_factor': overall.get('profit_factor', 0),
            'issues_count': len(self.last_issues),
            'recommendations_count': len(self.last_recommendations)
        }

    def format_recommendations_text(self, max_count: int = 3) -> str:
        """
        Format recommendations as text for display.

        Args:
            max_count: Maximum recommendations to format

        Returns:
            Formatted text
        """
        if not self.last_recommendations:
            return "No recommendations yet. Waiting for sufficient trade data."

        return self.recommender.format_recommendations_for_display(
            self.last_recommendations,
            max_display=max_count
        )

    def is_running(self) -> bool:
        """Check if agent is running."""
        return self.running

    def get_next_analysis_time(self) -> Optional[datetime]:
        """Get estimated time of next analysis."""
        if not self.last_analysis_time:
            return None

        return self.last_analysis_time + timedelta(hours=self.analysis_interval_hours)

    def get_time_until_next_analysis(self) -> Optional[timedelta]:
        """Get time remaining until next analysis."""
        next_time = self.get_next_analysis_time()
        if not next_time:
            return None

        return next_time - datetime.now()
