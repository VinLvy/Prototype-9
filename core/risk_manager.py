import logging
from typing import Dict, Any

class RiskManager:
    """
    RiskManager provides a centralized checking layer before trades are executed.
    Enforces maximum position sizes, daily limits, and open order constraints.
    """

    def __init__(self, max_position_usd: float = 50.0, daily_loss_limit: float = 30.0, max_open_positions: int = 3):
        self.max_position_usd = max_position_usd
        self.daily_loss_limit = daily_loss_limit
        self.max_open_positions = max_open_positions
        
        self.current_open_positions = 0
        self.current_daily_loss = 0.0
        self.logger = logging.getLogger(self.__class__.__name__)

    def evaluate_trade(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate if a trading signal passes all risk filters.
        
        Returns:
            Dict: Result containing {"allowed": bool, "reason": str, "recommended_size_usd": float}
        """
        # Circuit Breaker 1: Daily Loss
        if self.current_daily_loss >= self.daily_loss_limit:
            return {
                "allowed": False, 
                "reason": f"Daily loss limit reached (${self.current_daily_loss:.2f} >= ${self.daily_loss_limit:.2f})"
            }

        # Circuit Breaker 2: Max Open Positions
        if self.current_open_positions >= self.max_open_positions:
            return {
                "allowed": False, 
                "reason": f"Maximum open positions matched ({self.max_open_positions})"
            }
        
        # Calculate Position Size (Placeholder for Kelly Criterion calculation)
        # We will use half-kelly later. For now, max or dynamic default.
        recommended_size = min(self.max_position_usd, 25.0) 

        return {
            "allowed": True,
            "reason": "OK",
            "recommended_size_usd": recommended_size
        }

    def register_position(self, market_id: str):
        """Called by Execution Engine after a position is successfully taken."""
        self.current_open_positions += 1
        # self.logger.debug(f"Position opened. Current open: {self.current_open_positions}")

    def clear_position(self, market_id: str, pnl: float):
        """Should be called when a market resolves to free up margin."""
        self.current_open_positions = max(0, self.current_open_positions - 1)
        if pnl < 0:
            self.current_daily_loss += abs(pnl)
