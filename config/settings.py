"""
config/settings.py
-------------------
Centralised configuration loader for Prototype-9.
Reads from environment variables (via .env loaded by python-dotenv).
All other modules should import settings from here — never call os.getenv directly.
"""

import os
import logging
from dotenv import load_dotenv

# Load .env file from project root (safe no-op if not found)
load_dotenv()

logger = logging.getLogger(__name__)


def _get(key: str, default: str = "") -> str:
    val = os.getenv(key, default)
    if not val and not default:
        logger.warning(f"Environment variable '{key}' is not set.")
    return val


def _get_float(key: str, default: float = 0.0) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        logger.error(f"Invalid float value for '{key}'. Using default: {default}")
        return default


def _get_int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        logger.error(f"Invalid int value for '{key}'. Using default: {default}")
        return default


# ---------------------------------------------------------------------------
# Polymarket CLOB API
# ---------------------------------------------------------------------------
POLY_API_KEY: str = _get("POLY_API_KEY")
POLY_API_SECRET: str = _get("POLY_API_SECRET")
POLY_PASSPHRASE: str = _get("POLY_PASSPHRASE")

# ---------------------------------------------------------------------------
# Wallet (Polygon)
# ---------------------------------------------------------------------------
WALLET_PRIVATE_KEY: str = _get("WALLET_PRIVATE_KEY")
WALLET_ADDRESS: str = _get("WALLET_ADDRESS")

# ---------------------------------------------------------------------------
# Trading Parameters
# ---------------------------------------------------------------------------
MIN_SPREAD: float = _get_float("MIN_SPREAD", 0.020)
MAX_POSITION_USD: float = _get_float("MAX_POSITION_USD", 50.0)
DAILY_LOSS_LIMIT: float = _get_float("DAILY_LOSS_LIMIT", 30.0)
MAX_OPEN_POSITIONS: int = _get_int("MAX_OPEN_POSITIONS", 3)

# ---------------------------------------------------------------------------
# Mode
# ---------------------------------------------------------------------------
TRADING_MODE: str = _get("TRADING_MODE", "paper").lower()  # 'paper' | 'live'

# ---------------------------------------------------------------------------
# Gas (Polygon)
# ---------------------------------------------------------------------------
MAX_GAS_GWEI: float = _get_float("MAX_GAS_GWEI", 100.0)
GAS_PRICE_BUFFER: float = _get_float("GAS_PRICE_BUFFER", 1.2)

# ---------------------------------------------------------------------------
# Logging / DB
# ---------------------------------------------------------------------------
LOG_LEVEL: str = _get("LOG_LEVEL", "INFO").upper()
DB_PATH: str = _get("DB_PATH", "./data/trades.db")


def validate():
    """
    Validate critical settings are present for live mode.
    Call this at startup when TRADING_MODE == 'live'.
    """
    live_required = [
        ("POLY_API_KEY", POLY_API_KEY),
        ("POLY_API_SECRET", POLY_API_SECRET),
        ("POLY_PASSPHRASE", POLY_PASSPHRASE),
        ("WALLET_PRIVATE_KEY", WALLET_PRIVATE_KEY),
        ("WALLET_ADDRESS", WALLET_ADDRESS),
    ]
    missing = [k for k, v in live_required if not v]
    if missing:
        raise EnvironmentError(
            f"Live mode requires these env vars to be set: {missing}"
        )
    logger.info("Settings validation passed for LIVE mode.")


def summary() -> dict:
    """Return a non-sensitive summary dict for logging at startup."""
    return {
        "mode": TRADING_MODE,
        "min_spread": MIN_SPREAD,
        "max_position_usd": MAX_POSITION_USD,
        "daily_loss_limit": DAILY_LOSS_LIMIT,
        "max_open_positions": MAX_OPEN_POSITIONS,
        "max_gas_gwei": MAX_GAS_GWEI,
        "log_level": LOG_LEVEL,
        "db_path": DB_PATH,
    }
