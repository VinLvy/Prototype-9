import pytest
import time
from datetime import datetime, timezone, timedelta
from core.bonereaper_detector import BoneReaperDetector
import config.settings as settings

@pytest.fixture
def detector():
    # Setup standard paper context limits
    settings.ENTRY_PRICE_THRESHOLD = 0.35
    settings.HEDGE_TRIGGER_SECONDS = 120
    settings.MAX_COMBINED_COST = 0.97
    settings.MAX_POSITION_USD = 1.00
    
    return BoneReaperDetector(risk_manager=None)

def test_initial_state_idle(detector):
    assert len(detector.market_states) == 0

def test_entry_condition(detector):
    tick = {
        "market_id": "market-1",
        "yes_token_id": "yes-1",
        "no_token_id": "no-1",
        "yes_price": 0.30,  # below 0.35 threshold
        "no_price": 0.70,
        "timestamp": time.time() * 1000
    }
    
    signal = detector.calculate_signal(tick)
    assert signal is not None
    assert signal["side"] == "YES"
    assert signal["reason"] == "ENTRY"
    assert signal["execution_price"] == 0.30
    assert "recommended_size_usd" in signal
    
    state = detector.market_states["market-1"]
    assert state["state"] == "ENTERED"
    assert state["entry_side"] == "YES"
    
def test_unfulfilled_entry(detector):
    # Prices above threshold
    tick = {
        "market_id": "market-2",
        "yes_token_id": "yes-2",
        "no_token_id": "no-2",
        "yes_price": 0.40,
        "no_price": 0.60,
        "timestamp": time.time() * 1000
    }
    
    signal = detector.calculate_signal(tick)
    assert signal is None
    state = detector.market_states["market-2"]
    assert state["state"] == "IDLE"

def test_successful_hedge(detector):
    # 1. Enter
    current_time = time.time()
    tick1 = {
        "market_id": "market-3",
        "yes_token_id": "yes-3",
        "no_token_id": "no-3",
        "yes_price": 0.30,
        "no_price": 0.70,
        "timestamp": current_time * 1000
    }
    detector.calculate_signal(tick1)
    
    # 2. Fast forward 130 seconds (past 120s trigger)
    # And other side price drops to 0.65 -> Combined = 0.30 + 0.65 = 0.95 (<= 0.97)
    tick2 = {
        "market_id": "market-3", 
        "yes_token_id": "yes-3",
        "no_token_id": "no-3",
        "yes_price": 0.25,
        "no_price": 0.65,
        "timestamp": (current_time + 130) * 1000
    }
    
    signal = detector.calculate_signal(tick2)
    assert signal is not None
    assert signal["reason"] == "HEDGE"
    assert signal["side"] == "NO"
    assert signal["execution_price"] == 0.65
    assert detector.market_states["market-3"]["state"] == "HEDGED"
    
def test_denied_hedge(detector):
    # 1. Enter
    current_time = time.time()
    tick1 = {
        "market_id": "market-4",
        "yes_token_id": "y4", "no_token_id": "n4",
        "yes_price": 0.30, "no_price": 0.70,
        "timestamp": current_time * 1000
    }
    detector.calculate_signal(tick1)
    
    # 2. Fast forward but combined cost > 0.97
    # 0.30 + 0.80 = 1.10
    tick2 = {
         "market_id": "market-4",
         "yes_token_id": "y4", "no_token_id": "n4",
         "yes_price": 0.20, "no_price": 0.80,
         "timestamp": (current_time + 130) * 1000
    }
    signal = detector.calculate_signal(tick2)
    assert signal is None
    assert detector.market_states["market-4"]["state"] == "ENTERED"

def test_60_second_cut_loss(detector):
    current_time = time.time()
    tick1 = {
        "market_id": "market-5",
        "yes_token_id": "y5", "no_token_id": "n5",
        "yes_price": 0.30, "no_price": 0.70,
        "timestamp": current_time * 1000,
        "end_date_iso": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    }
    detector.calculate_signal(tick1)
    
    # Next tick is 30 seconds before close
    tick2 = {
        "market_id": "market-5",
        "yes_token_id": "y5", "no_token_id": "n5",
        "yes_price": 0.05, "no_price": 0.98, # Extremely bad price
        "timestamp": (current_time + 270) * 1000,
        "end_date_iso": (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
    }
    
    signal = detector.calculate_signal(tick2)
    assert signal is not None
    assert signal["reason"] == "CUT_LOSS"
    assert signal["side"] == "NO"
    assert detector.market_states["market-5"]["state"] == "HEDGED"
