"""
tests/test_detector.py
-----------------------
Unit tests for ArbitrageDetector.calculate_spread()
"""

import pytest
from core.arb_detector import ArbitrageDetector


@pytest.fixture
def detector():
    """Default detector with 2% min spread threshold."""
    return ArbitrageDetector(min_spread_threshold=0.020)


def _tick(yes: float, no: float, market_id: str = "BTC-UP-DOWN-15M") -> dict:
    return {"market_id": market_id, "yes_price": yes, "no_price": no, "timestamp": 0.0}


class TestCalculateSpread:

    def test_valid_opportunity_detected(self, detector):
        """Combined price of 1.04 > 1.025 threshold → signal returned."""
        signal = detector.calculate_spread(_tick(0.54, 0.50))
        assert signal is not None
        assert signal["market_id"] == "BTC-UP-DOWN-15M"
        assert signal["spread"] == pytest.approx(0.04, abs=1e-9)

    def test_no_opportunity_below_threshold(self, detector):
        """Combined price of 1.01 < 1.025 threshold → None returned."""
        signal = detector.calculate_spread(_tick(0.51, 0.50))
        assert signal is None

    def test_exactly_at_threshold_triggers(self, detector):
        """Combined price exactly equals threshold → signal returned."""
        # threshold = 1.00 + 0.005 (gas) + 0.020 (min_spread) = 1.025
        signal = detector.calculate_spread(_tick(0.525, 0.50))
        assert signal is not None

    def test_signal_fields_present(self, detector):
        """Returned signal contains all required keys."""
        signal = detector.calculate_spread(_tick(0.60, 0.55))
        assert signal is not None
        for key in ("market_id", "yes_price", "no_price", "spread", "estimated_profit_per_share", "timestamp"):
            assert key in signal, f"Missing key: {key}"

    def test_estimated_profit_is_spread_minus_gas(self, detector):
        """estimated_profit_per_share = spread - simulated_gas_factor (0.005)."""
        signal = detector.calculate_spread(_tick(0.60, 0.55))
        expected = signal["spread"] - 0.005
        assert signal["estimated_profit_per_share"] == pytest.approx(expected, abs=1e-9)

    def test_custom_threshold(self):
        """Detector with higher threshold rejects smaller spreads."""
        strict = ArbitrageDetector(min_spread_threshold=0.050)
        assert strict.calculate_spread(_tick(0.53, 0.50)) is None  # 3% < 5% + 0.5%

    def test_missing_prices_treated_as_zero(self, detector):
        """Missing yes/no price defaults to 0.0 → no opportunity."""
        signal = detector.calculate_spread({"market_id": "X", "timestamp": 0.0})
        assert signal is None

    def test_different_market_id_passes_through(self, detector):
        """market_id in tick is preserved correctly in signal."""
        signal = detector.calculate_spread(_tick(0.60, 0.55, "ETH-UP-DOWN-5M"))
        assert signal is not None
        assert signal["market_id"] == "ETH-UP-DOWN-5M"
