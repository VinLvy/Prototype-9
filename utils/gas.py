"""
Gas Estimator — Polygon Network
---------------------------------
Estimates the USD cost of executing a transaction on Polygon,
given current MATIC price and gas usage. Used by ArbitrageDetector
to decide whether the spread is wide enough to cover fees.

In Alpha v0.1 this uses static/mock values.
Live implementation should query:
  - Gas price: https://gasstation.polygon.technology/v2
  - MATIC/USD: Binance or CoinGecko REST API
"""

import logging
import asyncio
from typing import Optional


# Typical gas units for a simple ERC-20 transfer on Polygon CLOB
TYPICAL_GAS_UNITS = 120_000  # conservative estimate for dual-side order
GWEI_TO_MATIC = 1e-9


class GasEstimator:
    """
    Estimates transaction costs in USD for Polygon-based CLOB orders.
    """

    def __init__(
        self,
        max_gas_gwei: float = 100.0,
        gas_price_buffer: float = 1.2,
        matic_usd_price: float = 0.85,  # fallback static price
    ):
        """
        Args:
            max_gas_gwei (float): Maximum acceptable gas price in Gwei.
            gas_price_buffer (float): Multiplier applied to raw gas estimate (safety margin).
            matic_usd_price (float): Current MATIC / USD rate (updated periodically).
        """
        self.max_gas_gwei = max_gas_gwei
        self.gas_price_buffer = gas_price_buffer
        self.matic_usd_price = matic_usd_price
        self.logger = logging.getLogger(self.__class__.__name__)

        # Cached current gas price
        self._current_gas_gwei: float = 30.0  # sane Polygon default

    def estimate_cost_usd(self, gas_units: int = TYPICAL_GAS_UNITS) -> float:
        """
        Estimate the USD cost of one dual-side arbitrage execution.

        Args:
            gas_units (int): Number of gas units consumed.

        Returns:
            float: Estimated fee in USD.
        """
        gas_gwei = self._current_gas_gwei * self.gas_price_buffer
        gas_matic = gas_gwei * GWEI_TO_MATIC * gas_units
        gas_usd = gas_matic * self.matic_usd_price

        self.logger.debug(
            f"Gas estimate | {gas_gwei:.1f} Gwei × {gas_units} units "
            f"= {gas_matic:.6f} MATIC = ${gas_usd:.4f}"
        )
        return round(gas_usd, 6)

    def is_gas_acceptable(self) -> bool:
        """Returns True if current gas price is within our configured limit."""
        return self._current_gas_gwei <= self.max_gas_gwei

    async def refresh(self):
        """
        Fetch live gas price and MATIC/USD from external APIs.
        Catches exceptions and gracefully falls back to previous values.
        """
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                # 1. Fetch Polygon Gas
                async with session.get("https://gasstation.polygon.technology/v2", timeout=5) as gas_resp:
                    if gas_resp.status == 200:
                        gas_data = await gas_resp.json()
                        # Use 'fast' maxFee, fallback to 'safeLow' if needed
                        fast_gas = gas_data.get("fast", {}).get("maxFee", 0)
                        if fast_gas > 0:
                            self._current_gas_gwei = round(float(fast_gas), 1)

                # 2. Fetch MATIC USD price
                async with session.get("https://api.binance.com/api/v3/ticker/price?symbol=MATICUSDT", timeout=5) as price_resp:
                    if price_resp.status == 200:
                        price_data = await price_resp.json()
                        matic_price = float(price_data.get("price", 0.0))
                        if matic_price > 0:
                            self.matic_usd_price = round(matic_price, 4)
                            
        except Exception as e:
            self.logger.warning(f"Failed to fetch live gas/price data: {e}. Using cached values.")

        self.logger.debug(
            f"Gas refreshed: {self._current_gas_gwei} Gwei | "
            f"MATIC: ${self.matic_usd_price}"
        )

    def as_percentage_of_spread(self, spread_usd: float, position_usd: float) -> float:
        """
        Return gas cost as a fraction of the expected profit.
        Used to skip trades where fees consume >30% of spread.

        Args:
            spread_usd (float): Absolute spread profit (spread_pct × position_usd).
            position_usd (float): Trade size.

        Returns:
            float: Gas as a fraction of spread profit (e.g. 0.28 = 28%).
        """
        if spread_usd <= 0:
            return float("inf")
        gas_cost = self.estimate_cost_usd()
        return gas_cost / spread_usd
