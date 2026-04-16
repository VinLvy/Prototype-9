"""
tests/test_kelly.py
--------------------
Unit tests for KellyCriterion.compute()
"""

import pytest
from utils.kelly import KellyCriterion


@pytest.fixture
def kelly():
    return KellyCriterion(bankroll=1000.0, use_half_kelly=True)


class TestKellyCompute:

    def test_positive_edge_returns_nonzero_size(self, kelly):
        """With clear edge, Kelly should recommend a positive position."""
        size = kelly.compute(win_probability=0.75, profit_on_win=0.03, loss_on_loss=1.0)
        assert size > 0

    def test_no_edge_returns_zero(self, kelly):
        """No positive edge (p=0.50, b=0.03) → Kelly fraction negative → return 0."""
        size = kelly.compute(win_probability=0.50, profit_on_win=0.03, loss_on_loss=1.0)
        assert size == 0.0

    def test_max_cap_applied(self, kelly):
        """Result should not exceed max_position_usd."""
        size = kelly.compute(
            win_probability=0.99,
            profit_on_win=0.50,
            loss_on_loss=1.0,
            max_position_usd=25.0,
        )
        assert size <= 25.0

    def test_half_kelly_smaller_than_full_kelly(self):
        """Half-Kelly should be exactly 50% of full Kelly."""
        full = KellyCriterion(bankroll=1000.0, use_half_kelly=False)
        half = KellyCriterion(bankroll=1000.0, use_half_kelly=True)
        f = full.compute(win_probability=0.75, profit_on_win=0.05, loss_on_loss=1.0)
        h = half.compute(win_probability=0.75, profit_on_win=0.05, loss_on_loss=1.0)
        assert h == pytest.approx(f / 2, abs=0.01)

    def test_invalid_win_probability_zero(self, kelly):
        """win_probability=0 is invalid, should return 0."""
        size = kelly.compute(win_probability=0.0, profit_on_win=0.05, loss_on_loss=1.0)
        assert size == 0.0

    def test_invalid_win_probability_one(self, kelly):
        """win_probability=1.0 is invalid (certainty), should return 0."""
        size = kelly.compute(win_probability=1.0, profit_on_win=0.05, loss_on_loss=1.0)
        assert size == 0.0

    def test_invalid_profit_returns_zero(self, kelly):
        size = kelly.compute(win_probability=0.75, profit_on_win=0.0, loss_on_loss=1.0)
        assert size == 0.0

    def test_position_scales_with_bankroll(self):
        """Doubling bankroll should double recommended size."""
        k1 = KellyCriterion(bankroll=500.0)
        k2 = KellyCriterion(bankroll=1000.0)
        s1 = k1.compute(0.75, 0.03, 1.0)
        s2 = k2.compute(0.75, 0.03, 1.0)
        assert s2 == pytest.approx(s1 * 2, abs=0.01)

    def test_update_bankroll(self, kelly):
        kelly.update_bankroll(1500.0)
        assert kelly.bankroll == 1500.0
        size = kelly.compute(0.75, 0.03, 1.0)
        # Should produce larger size with bigger bankroll
        assert size > 0
