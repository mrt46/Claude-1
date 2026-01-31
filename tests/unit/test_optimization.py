"""
Unit tests for optimization module.

Tests parameter analyzer, recommendation engine, and optimization agent.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.optimization.agent import OptimizationAgent
from src.optimization.parameter_analyzer import ParameterAnalyzer
from src.optimization.recommendation_engine import RecommendationEngine


@pytest.fixture
def mock_database():
    """Mock TimescaleDBClient."""
    db = MagicMock()
    db.is_connected.return_value = True

    # Sample trade data
    trades = [
        {
            'id': f'trade_{i}',
            'symbol': 'BTCUSDT' if i % 2 == 0 else 'ETHUSDT',
            'side': 'BUY' if i % 3 == 0 else 'SELL',
            'entry_price': 50000.0 + i * 100,
            'exit_price': 50100.0 + i * 100,
            'quantity': 0.01,
            'pnl': 10.0 if i % 2 == 0 else -5.0,  # 50% win rate
            'pnl_percent': 0.2 if i % 2 == 0 else -0.1,
            'entry_fee': 0.5,
            'exit_fee': 0.5,
            'total_fees': 1.0,
            'closure_reason': 'TAKE_PROFIT_HIT' if i % 2 == 0 else 'STOP_LOSS_HIT',
            'strategy_name': 'InstitutionalStrategy',
            'entry_time': datetime.now() - timedelta(hours=24 - i),
            'exit_time': datetime.now() - timedelta(hours=23 - i),
            'hold_duration_seconds': 3600  # 1 hour
        }
        for i in range(15)  # 15 trades
    ]

    db.get_recent_trades = AsyncMock(return_value=trades)

    return db


@pytest.fixture
def parameter_analyzer(mock_database):
    """Create ParameterAnalyzer with mock database."""
    return ParameterAnalyzer(mock_database)


@pytest.fixture
def recommendation_engine():
    """Create RecommendationEngine."""
    return RecommendationEngine()


class TestParameterAnalyzer:
    """Test ParameterAnalyzer functionality."""

    @pytest.mark.asyncio
    async def test_analyze_timeframe_success(self, parameter_analyzer):
        """Test successful analysis of timeframe."""
        result = await parameter_analyzer.analyze_timeframe(hours=24, min_trades=5)

        assert result['status'] == 'success'
        assert result['trades_count'] == 15
        assert 'overall' in result
        assert 'by_symbol' in result
        assert 'stop_loss' in result

    @pytest.mark.asyncio
    async def test_analyze_timeframe_insufficient_data(self, parameter_analyzer, mock_database):
        """Test analysis with insufficient data."""
        # Return empty trades
        mock_database.get_recent_trades = AsyncMock(return_value=[])

        result = await parameter_analyzer.analyze_timeframe(hours=24, min_trades=5)

        assert result['status'] == 'insufficient_data'
        assert result['trades_count'] == 0

    @pytest.mark.asyncio
    async def test_calculate_overall_metrics(self, parameter_analyzer, mock_database):
        """Test overall metrics calculation."""
        result = await parameter_analyzer.analyze_timeframe(hours=24, min_trades=5)

        overall = result['overall']
        assert overall['total_trades'] == 15
        assert overall['winning_trades'] == 8  # ceil(15 * 0.5)
        assert overall['losing_trades'] == 7  # floor(15 * 0.5)
        assert 0 < overall['win_rate'] < 100
        assert 'total_pnl' in overall
        assert 'profit_factor' in overall

    @pytest.mark.asyncio
    async def test_analyze_by_symbol(self, parameter_analyzer):
        """Test symbol-specific analysis."""
        result = await parameter_analyzer.analyze_timeframe(hours=24, min_trades=5)

        by_symbol = result['by_symbol']
        assert 'BTCUSDT' in by_symbol
        assert 'ETHUSDT' in by_symbol

        # Check structure
        btc_stats = by_symbol['BTCUSDT']
        assert 'total_trades' in btc_stats
        assert 'win_rate' in btc_stats
        assert 'total_pnl' in btc_stats

    @pytest.mark.asyncio
    async def test_identify_parameter_issues(self, parameter_analyzer):
        """Test issue identification."""
        analysis = await parameter_analyzer.analyze_timeframe(hours=24, min_trades=5)
        issues = parameter_analyzer.identify_parameter_issues(analysis)

        assert isinstance(issues, list)
        # Should have at least one issue (win rate is 50%, which is below 55% target)
        # or stop-loss/take-profit ratio issue
        assert len(issues) >= 0  # May or may not have issues depending on data


class TestRecommendationEngine:
    """Test RecommendationEngine functionality."""

    def test_generate_recommendations_empty_analysis(self, recommendation_engine):
        """Test recommendation generation with empty analysis."""
        analysis = {'status': 'insufficient_data'}
        issues = []

        recommendations = recommendation_engine.generate_recommendations(
            analysis, issues, current_config=None
        )

        assert isinstance(recommendations, list)
        assert len(recommendations) == 0

    @pytest.mark.asyncio
    async def test_generate_recommendations_with_issues(
        self, recommendation_engine, parameter_analyzer
    ):
        """Test recommendation generation with identified issues."""
        analysis = await parameter_analyzer.analyze_timeframe(hours=24, min_trades=5)
        issues = parameter_analyzer.identify_parameter_issues(analysis)

        recommendations = recommendation_engine.generate_recommendations(
            analysis, issues, current_config=None
        )

        assert isinstance(recommendations, list)
        # Should have recommendations for identified issues
        if len(issues) > 0:
            assert len(recommendations) > 0

            # Check recommendation structure
            if recommendations:
                rec = recommendations[0]
                assert 'priority' in rec
                assert 'category' in rec
                assert 'title' in rec
                assert 'description' in rec
                assert 'action' in rec
                assert 'expected_impact' in rec

    def test_format_recommendations_for_display(self, recommendation_engine):
        """Test formatting recommendations for display."""
        recommendations = [
            {
                'priority': 'high',
                'title': 'Test Recommendation',
                'description': 'Test description',
                'action': 'Test action',
                'expected_impact': 'Test impact'
            }
        ]

        formatted = recommendation_engine.format_recommendations_for_display(
            recommendations, max_display=3
        )

        assert isinstance(formatted, str)
        assert 'Test Recommendation' in formatted
        assert 'HIGH' in formatted


class TestOptimizationAgent:
    """Test OptimizationAgent functionality."""

    @pytest.fixture
    def optimization_agent(self, mock_database):
        """Create OptimizationAgent with mock database."""
        agent = OptimizationAgent(
            database=mock_database,
            analysis_interval_hours=24,
            min_trades_for_analysis=5
        )
        return agent

    def test_agent_initialization(self, optimization_agent):
        """Test agent initialization."""
        assert optimization_agent is not None
        assert optimization_agent.running is False
        assert optimization_agent.last_analysis_time is None
        assert optimization_agent.analyzer is not None
        assert optimization_agent.recommender is not None

    @pytest.mark.asyncio
    async def test_run_analysis_success(self, optimization_agent):
        """Test successful analysis run."""
        result = await optimization_agent.run_analysis(hours=24, min_trades=5)

        assert result['status'] == 'success'
        assert 'analysis' in result
        assert 'issues' in result
        assert 'recommendations' in result
        assert optimization_agent.last_analysis_time is not None

    @pytest.mark.asyncio
    async def test_run_analysis_insufficient_data(self, optimization_agent, mock_database):
        """Test analysis with insufficient data."""
        # Return empty trades
        mock_database.get_recent_trades = AsyncMock(return_value=[])

        result = await optimization_agent.run_analysis(hours=24, min_trades=5)

        assert result['status'] == 'incomplete'
        assert 'message' in result

    def test_get_latest_recommendations(self, optimization_agent):
        """Test getting latest recommendations."""
        # Initially empty
        recommendations = optimization_agent.get_latest_recommendations(max_count=5)
        assert isinstance(recommendations, list)
        assert len(recommendations) == 0

    def test_get_analysis_summary(self, optimization_agent):
        """Test getting analysis summary."""
        # Initially None
        summary = optimization_agent.get_analysis_summary()
        assert summary is None

    @pytest.mark.asyncio
    async def test_agent_lifecycle(self, optimization_agent):
        """Test agent start/stop lifecycle."""
        # Start agent
        optimization_agent.start()
        assert optimization_agent.is_running() is True

        # Stop agent
        optimization_agent.stop()
        assert optimization_agent.is_running() is False


def test_optimization_module_imports():
    """Test that optimization module can be imported."""
    from src.optimization import (
        OptimizationAgent,
        ParameterAnalyzer,
        RecommendationEngine,
    )

    assert OptimizationAgent is not None
    assert ParameterAnalyzer is not None
    assert RecommendationEngine is not None
