import logging
from typing import Dict, Any

class RiskManager:
    """
    RiskManager provides a centralized checking layer before trades are executed.
    Enforces maximum position sizes, daily limits, and open order constraints.
    Tracks asymmetric positions (YES vs NO) independently per market.
    """

    def __init__(self, max_position_usd: float = 50.0, daily_loss_limit: float = 30.0, max_open_positions: int = 3):
        self.max_position_usd = max_position_usd
        self.daily_loss_limit = daily_loss_limit
        self.max_open_positions = max_open_positions
        
        self.current_daily_loss = 0.0
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Track exposure per market
        # Format: { "market_id": { "yes_exposure": float, "no_exposure": float, "net_cost": float } }
        self.positions: Dict[str, Dict[str, Any]] = {}

    def get_position(self, market_id: str) -> Dict[str, Any]:
        """Get the current tracking state for a specific market."""
        return self.positions.get(market_id, {
            "yes_exposure": 0.0,
            "no_exposure": 0.0,
            "net_cost": 0.0,
            "yes_price": 0.0,
            "no_price": 0.0
        })

    def evaluate_trade(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate if a trading signal passes all risk filters.
        Expects signal to specify 'side' ("YES" or "NO") if asymmetric,
        or handles legacy combined signals.
        """
        # Circuit Breaker 1: Daily Loss
        if self.current_daily_loss >= self.daily_loss_limit:
            return {
                "allowed": False, 
                "reason": f"Daily loss limit reached (${self.current_daily_loss:.2f} >= ${self.daily_loss_limit:.2f})"
            }

        market_id = signal.get("market_id")
        current_pos = self.get_position(market_id)
        
        # Circuit Breaker 2: Max Open Positions
        if current_pos["net_cost"] == 0 and len(self.positions) >= self.max_open_positions:
            return {
                "allowed": False, 
                "reason": f"Maximum open positions matched ({self.max_open_positions})"
            }
            
        side = signal.get("side") # "YES" or "NO"
        if side == "YES" and current_pos["yes_exposure"] > 0:
            return {"allowed": False, "reason": "Already hold YES exposure for this market"}
        if side == "NO" and current_pos["no_exposure"] > 0:
            return {"allowed": False, "reason": "Already hold NO exposure for this market"}

        # Calculate Position Size (Placeholder for Kelly Criterion calculation)
        recommended_size = min(self.max_position_usd, 25.0) 

        return {
            "allowed": True,
            "reason": "OK",
            "recommended_size_usd": recommended_size
        }

    def register_leg_fill(self, market_id: str, side: str, price: float, size_usd: float):
        """Called by Execution Engine after a specific leg is filled."""
        if market_id not in self.positions:
            self.positions[market_id] = {
                "yes_exposure": 0.0,
                "no_exposure": 0.0,
                "net_cost": 0.0,
                "yes_price": 0.0,
                "no_price": 0.0
            }
            
        pos = self.positions[market_id]
        if side == "YES":
            pos["yes_exposure"] += size_usd
            pos["yes_price"] = price
        elif side == "NO":
            pos["no_exposure"] += size_usd
            pos["no_price"] = price
            
        pos["net_cost"] += size_usd

    def register_position(self, market_id: str):
        """Legacy fallback: simply touch the position map to count as open."""
        if market_id not in self.positions:
            self.positions[market_id] = {
                "yes_exposure": 1.0, 
                "no_exposure": 1.0, 
                "net_cost": 1.0
            }

    def clear_position(self, market_id: str, pnl: float):
        """Should be called when a market resolves to free up margin."""
        if market_id in self.positions:
            del self.positions[market_id]
            
        if pnl < 0:
            self.current_daily_loss += abs(pnl)
