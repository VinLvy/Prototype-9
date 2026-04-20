import logging
import asyncio
from typing import Dict, Any
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
    It supports 'paper' and 'live' modes.
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
            
    async def execute_arbitrage(self, signal: Dict[str, Any]) -> bool:
        """
        Executes a single-sided leg order based on the Asymmetric signal.
        """
        market_id = signal.get("market_id")
        side = signal.get("side") # "YES" or "NO"
        token_id = signal.get("yes_token_id") if side == "YES" else signal.get("no_token_id")
        execution_price = signal.get("execution_price", 0.0)
        
        # 1. Ask RiskManager if we are allowed to take this trade
        risk_evaluation = self.risk_manager.evaluate_trade(signal)
        if not risk_evaluation.get("allowed"):
            self.logger.warning(f"Trade rejected by RiskManager: {risk_evaluation.get('reason')}")
            return False

        position_size = risk_evaluation.get("recommended_size_usd", 10.0)
        
        # Approximate size in shares to buy
        if execution_price > 0:
            share_size = round(position_size / execution_price, 2)
        else:
            share_size = 0.0

        self.logger.info(
            f"Executing {side} leg | Mode: {self.mode.upper()} "
            f"| Size: ${position_size:.2f} ({share_size} shares) | Token: {str(token_id)[:10]}..."
        )

        # 2. API Execution
        await asyncio.sleep(0.1) # 100ms realistic mock latency
        
        if self.mode == "live":
            try:
                # FOK Limit order
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
                    return False
            except Exception as e:
                self.logger.error(f"CLOB Request Exception: {e}")
                return False
                
        elif self.mode == "paper":
            import random
            if random.random() > 0.75:
                self.logger.warning(f"Paper mode: Execution FAILED (simulated liquidity miss)")
                return False
        else:
            self.logger.error(f"Unknown mode '{self.mode}'")
            return False

        # 3. Log the successful execution
        estimated_profit = position_size * signal.get("estimated_profit_per_share", 0.0)
        self.data_logger.log_trade({
            "market_id": market_id,
            "mode": self.mode,
            "size_usd": position_size,
            "spread": signal.get("spread", 0.0),
            "estimated_profit": estimated_profit,
            "status": "WIN" if self.mode == "paper" else "FILLED"
        })
        
        self.risk_manager.register_leg_fill(market_id, side, execution_price, position_size)
        self.logger.info(f"Executed {side} on {market_id[:30]} | Filled @ {execution_price:.3f}")

        return True
