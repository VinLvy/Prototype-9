"""
tests/test_risk_manager.py
---------------------------
Unit tests for RiskManager.evaluate_trade() and position tracking.
"""

import pytest
from core.risk_manager import RiskManager


@pytest.fixture
def rm():
    return RiskManager(max_position_usd=50.0, daily_loss_limit=30.0, max_open_positions=3)


def _signal(spread: float = 0.03) -> dict:
    return {
        "market_id": "BTC-UP-DOWN-15M",
        "spread": spread,
        "yes_price": 0.52,
        "no_price": 0.51,
        "estimated_profit_per_share": spread - 0.005,
        "timestamp": 0.0,
    }


class TestEvaluateTrade:

    def test_trade_allowed_under_normal_conditions(self, rm):
        result = rm.evaluate_trade(_signal())
        assert result["allowed"] is True

    def test_recommended_size_within_max(self, rm):
        result = rm.evaluate_trade(_signal())
        assert result["recommended_size_usd"] <= rm.max_position_usd

    def test_daily_loss_circuit_breaker(self, rm):
        """If daily loss == limit, trade should be blocked."""
        rm.current_daily_loss = 30.0
        result = rm.evaluate_trade(_signal())
        assert result["allowed"] is False
        assert "daily loss" in result["reason"].lower()

    def test_daily_loss_just_under_limit_allows_trade(self, rm):
        rm.current_daily_loss = 29.99
        result = rm.evaluate_trade(_signal())
        assert result["allowed"] is True

    def test_max_open_positions_circuit_breaker(self, rm):
        """If open positions == max, trade should be blocked."""
        rm.current_open_positions = 3
        result = rm.evaluate_trade(_signal())
        assert result["allowed"] is False
        assert "position" in result["reason"].lower()

    def test_register_position_increments_count(self, rm):
        rm.register_position("MKT-1")
        assert rm.current_open_positions == 1

    def test_clear_position_decrements_count(self, rm):
        rm.register_position("MKT-1")
        rm.clear_position("MKT-1", pnl=0.50)
        assert rm.current_open_positions == 0

    def test_clear_position_loss_increments_daily_loss(self, rm):
        rm.clear_position("MKT-1", pnl=-5.00)
        assert rm.current_daily_loss == pytest.approx(5.00)

    def test_clear_position_win_does_not_increment_daily_loss(self, rm):
        rm.clear_position("MKT-1", pnl=+2.50)
        assert rm.current_daily_loss == 0.0

    def test_position_count_never_goes_negative(self, rm):
        rm.clear_position("MKT-NONEXISTENT", pnl=0.0)
        assert rm.current_open_positions == 0

    def test_both_circuit_breakers_tripped_returns_first_breaker(self, rm):
        rm.current_daily_loss = 30.0
        rm.current_open_positions = 3
        result = rm.evaluate_trade(_signal())
        assert result["allowed"] is False
