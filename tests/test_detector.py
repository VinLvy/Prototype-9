"""
tests/test_detector.py
-----------------------
Unit tests for ArbitrageDetector.calculate_spread()
"""

import pytest
from core.arb_detector import ArbitrageDetector
from core.risk_manager import RiskManager

@pytest.fixture
def risk_manager():
    return RiskManager(max_position_usd=50.0, daily_loss_limit=30.0, max_open_positions=3)

@pytest.fixture
def detector(risk_manager):
    """Default detector with 2% min spread threshold."""
    return ArbitrageDetector(min_spread_threshold=0.020, risk_manager=risk_manager)


def _tick(yes: float, no: float, market_id: str = "BTC-UP-DOWN-15M") -> dict:
    return {
        "market_id": market_id, 
        "condition_id": "0xABC123",
        "yes_token_id": "token_yes_1",
        "no_token_id": "token_no_1",
        "yes_price": yes, 
        "no_price": no, 
        "timestamp": 0.0
    }


class TestCalculateSpread:

    def test_rejects_combined_loss(self, detector):
        """Combined price of 1.04 > 0.975 target cost -> Should reject completely."""
        # 1.04 means we spend $1.04 to win $1.00. This is a guaranteed loss in Taker Buy.
        signal = detector.calculate_spread(_tick(0.54, 0.50))
        assert signal is None

    def test_asymmetric_entry_yes(self, detector):
        """When YES drops below fair value (0.4875), BUY YES."""
        signal = detector.calculate_spread(_tick(0.45, 0.60))
        assert signal is not None
        assert signal["side"] == "YES"
        assert signal["execution_price"] == 0.45

    def test_asymmetric_entry_no(self, detector):
        """When NO drops below fair value (0.4875), BUY NO."""
        signal = detector.calculate_spread(_tick(0.60, 0.48))
        assert signal is not None
        assert signal["side"] == "NO"
        assert signal["execution_price"] == 0.48

    def test_dynamic_hedge_no(self, detector, risk_manager):
        """If holding YES at 0.45, Target NO is 0.975 - 0.45 = 0.525. BUY NO if it hits 0.52."""
        risk_manager.register_leg_fill("BTC-UP-DOWN-15M", "YES", 0.45, 10.0)
        signal = detector.calculate_spread(_tick(0.45, 0.52))
        assert signal is not None
        assert signal["side"] == "NO"
        assert signal["execution_price"] == 0.52
        assert signal["spread"] == pytest.approx(1.00 - (0.45 + 0.52), abs=1e-9)

    def test_dynamic_hedge_no_rejected(self, detector, risk_manager):
        """If holding YES at 0.45, Target NO is 0.525. NO = 0.55 -> Reject NO."""
        risk_manager.register_leg_fill("BTC-UP-DOWN-15M", "YES", 0.45, 10.0)
        signal = detector.calculate_spread(_tick(0.45, 0.55))
        assert signal is None

    def test_missing_tokens_rejected(self, detector):
        """Ticks lacking token_ids MUST be rejected."""
        tick = _tick(0.40, 0.40)
        tick.pop("yes_token_id")
        assert detector.calculate_spread(tick) is None

    def test_signal_fields_present(self, detector):
        """Returned signal contains all required keys for downstream."""
        signal = detector.calculate_spread(_tick(0.45, 0.45))  # triggers YES
        assert signal is not None
        for key in ("market_id", "yes_price", "no_price", "spread", "estimated_profit_per_share", "timestamp", "side", "execution_price"):
            assert key in signal, f"Missing key: {key}"
