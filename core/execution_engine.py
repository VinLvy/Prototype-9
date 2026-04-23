import logging
import asyncio
import aiohttp
from typing import Dict, Any, Optional
from .risk_manager import RiskManager
from .data_logger import DataLogger
import config.settings as settings

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType, ApiCreds
    from py_clob_client.constants import POLYGON
    CLOB_AVAILABLE = True
except ImportError:
    CLOB_AVAILABLE = False

class ExecutionEngine:
    """
    ExecutionEngine handles placing orders across the Polymarket CLOB.
    Supports 'paper' and 'live' modes.

    Status logic (paper mode):
    - ENTRY signal  → status = "FILLED"  (leg open, not yet resolved)
    - HEDGE signal with spread > 0 → status = "WIN"
    - HEDGE signal with spread <= 0 → status = "LOSS" (paid too much combined)
    - CUT_LOSS signal → status = "LOSS" (forced hedge at bad price)
    """

    def __init__(self, mode: str, risk_manager: RiskManager, data_logger: DataLogger):
        self.mode = mode.lower()
        self.risk_manager = risk_manager
        self.data_logger = data_logger
        self.logger = logging.getLogger(self.__class__.__name__)
        self.client = None

        if self.mode == "live":
            if not CLOB_AVAILABLE:
                self.logger.critical("py-clob-client is not installed! Cannot run in live mode.")
                raise ImportError("py-clob-client required for live mode.")

            settings.validate()
            creds = ApiCreds(
                api_key=settings.POLY_API_KEY,
                api_secret=settings.POLY_API_SECRET,
                api_passphrase=settings.POLY_PASSPHRASE
            )
            self.client = ClobClient(
                "https://clob.polymarket.com",
                key=settings.WALLET_PRIVATE_KEY,
                chain_id=POLYGON,
                creds=creds
            )

    async def _check_liquidity(self, token_id: str, required_size: float) -> bool:
        """Check depth at best_ask level before placing order."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://clob.polymarket.com/book?token_id={token_id}"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        asks = data.get("asks", [])
                        if asks:
                            best_ask = asks[0]
                            available_size = float(best_ask.get("size", 0.0))
                            return available_size >= required_size
        except Exception as e:
            self.logger.error(f"Liquidity check failed for {token_id}: {e}")
        return False

    async def execute_arbitrage(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Executes a single-sided leg order based on the signal.
        Returns the trade_record dict if execution succeeded and was logged, else None.
        """
        market_id = signal.get("market_id")
        side = signal.get("side")  # "YES" or "NO"
        token_id = signal.get("yes_token_id") if side == "YES" else signal.get("no_token_id")
        execution_price = signal.get("execution_price", 0.0)
        reason = signal.get("reason", "")  # "ENTRY" | "HEDGE" | "CUT_LOSS" | ""

        # 1. Risk gate
        risk_evaluation = self.risk_manager.evaluate_trade(signal)
        if not risk_evaluation.get("allowed"):
            self.logger.warning(f"Trade rejected by RiskManager: {risk_evaluation.get('reason')}")
            return None

        position_size = risk_evaluation.get("recommended_size_usd", 10.0)

        if execution_price > 0:
            share_size = round(position_size / execution_price, 2)
        else:
            share_size = 0.0

        self.logger.info(
            f"Executing {side} leg [{reason}] | Mode: {self.mode.upper()} "
            f"| Size: ${position_size:.2f} ({share_size} shares) @ {execution_price:.3f}"
        )

        # 2. Simulated latency
        await asyncio.sleep(0.1)

        # 3. Order placement
        if self.mode == "live":
            has_liquidity = await self._check_liquidity(token_id, share_size)
            if not has_liquidity:
                self.logger.warning(f"Liquidity check failed: available size at best_ask < {share_size} for {token_id}")
                return None

            try:
                order_args = OrderArgs(
                    price=execution_price,
                    size=share_size,
                    side="BUY",
                    token_id=token_id
                )
                signed_order = self.client.create_order(order_args)
                resp = self.client.post_order(signed_order, order_type=OrderType.FOK)
                if getattr(resp, "error_msg", None) or getattr(resp, "success", False) is False:
                    self.logger.warning(f"Live mode execution failed: {resp}")
                    return None
            except Exception as e:
                self.logger.error(f"CLOB Request Exception: {e}")
                return None

        elif self.mode == "paper":
            pass # Selalu sukses di paper mode agar status state machine tetap tersinkron
        else:
            self.logger.error(f"Unknown mode '{self.mode}'")
            return None

        # 4. Determine status and realized P&L based on signal reason
        spread = signal.get("spread", 0.0)
        estimated_profit_per_share = signal.get("estimated_profit_per_share", 0.0)

        if self.mode == "paper":
            if reason == "HEDGE":
                if spread > 0 and estimated_profit_per_share > 0:
                    # Profitable hedge: combined cost < 1.00 - gas
                    status = "WIN"
                    estimated_profit = position_size * estimated_profit_per_share
                else:
                    # Hedge completed but spread negative = net loss
                    status = "LOSS"
                    estimated_profit = position_size * estimated_profit_per_share  # will be negative
            elif reason == "CUT_LOSS":
                # Forced hedge near market close at bad price
                status = "LOSS"
                actual_entry_price = signal.get("entry_price", execution_price)
                actual_combined = actual_entry_price + execution_price
                loss_spread = 1.00 - actual_combined
                estimated_profit = position_size * (loss_spread - 0.005)
            else:
                # ENTRY leg or unknown: position open, not yet resolved
                status = "FILLED"
                estimated_profit = 0.0  # unrealized
        else:
            # Live mode: actual resolution handled by blockchain
            status = "FILLED"
            estimated_profit = 0.0

        # 5. Log trade
        actual_entry_price = signal.get("entry_price", execution_price)
        trade_record = {
            "market_id": market_id,
            "mode": self.mode,
            "size_usd": position_size,
            "spread": spread,
            "estimated_profit": estimated_profit,
            "status": status,
            "reason": reason,
            "entry_price": actual_entry_price,
            "exit_price": execution_price if reason in ["HEDGE", "CUT_LOSS"] else 0.0
        }
        self.data_logger.log_trade(trade_record)

        self.risk_manager.register_leg_fill(market_id, side, execution_price, position_size)
        self.logger.info(
            f"Logged {status} | {side} on {str(market_id)[:30]} "
            f"@ {execution_price:.3f} | P&L: ${estimated_profit:.4f}"
        )

        return trade_record