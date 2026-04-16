"""
Shared Utility Helpers
-----------------------
Common formatting, math and time utilities used across Prototype-9 modules.
"""

import time
import datetime
from typing import Union


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_usd(value: float, sign: bool = False) -> str:
    """
    Format a float as a USD dollar string.

    Args:
        value (float): The dollar amount.
        sign (bool): If True, prefix positive values with '+'.

    Returns:
        str: e.g. "+$12.40" or "$-0.42"
    """
    prefix = "+" if sign and value >= 0 else ""
    return f"{prefix}${value:.2f}"


def format_pct(value: float, sign: bool = False) -> str:
    """
    Format a float as a percentage string (e.g. 0.024 → "2.40%").

    Args:
        value (float): Decimal ratio (0.0 – 1.0).
        sign (bool): If True, prefix positive values with '+'.

    Returns:
        str: e.g. "2.40%" or "+2.40%"
    """
    pct = value * 100
    prefix = "+" if sign and pct >= 0 else ""
    return f"{prefix}{pct:.2f}%"


def format_ts(ts: float) -> str:
    """
    Convert a Unix timestamp to a human-readable time string HH:MM:SS.

    Args:
        ts (float): Unix timestamp.

    Returns:
        str: e.g. "14:32:01"
    """
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------

def now_ts() -> float:
    """Return current time as a Unix timestamp float."""
    return time.time()


def now_str() -> str:
    """Return current time as HH:MM:SS string."""
    return datetime.datetime.now().strftime("%H:%M:%S")


def today_str() -> str:
    """Return today's date as YYYY-MM-DD string."""
    return datetime.datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Safe math
# ---------------------------------------------------------------------------

def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Division that returns `default` instead of raising ZeroDivisionError.

    Args:
        numerator (float): The dividend.
        denominator (float): The divisor.
        default (float): Fallback value when denominator is zero.

    Returns:
        float: Result or default.
    """
    if denominator == 0:
        return default
    return numerator / denominator


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp `value` to [min_val, max_val]."""
    return max(min_val, min(max_val, value))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def is_valid_price(price: Union[float, None]) -> bool:
    """Return True if price is a positive finite float."""
    if price is None:
        return False
    return isinstance(price, (int, float)) and 0.0 < price < float("inf")


def is_valid_market_id(market_id: str) -> bool:
    """Basic sanity check that market_id is a non-empty string."""
    return isinstance(market_id, str) and len(market_id.strip()) > 0
