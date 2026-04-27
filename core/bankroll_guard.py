import logging
import math

class BankrollGuard:
    """
    Capital tracker to ensure we don't exceed the total bankroll.
    Maintains available and deployed capital, and dynamically determines
    if a new position can be opened.
    """
    def __init__(self, initial_bankroll: float):
        self.initial_bankroll = initial_bankroll
        self.deployed_capital = 0.0
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    def available_capital(self) -> float:
        return self.initial_bankroll - self.deployed_capital

    @property
    def max_concurrent_positions(self) -> int:
        # Each full arb requires 2 legs, assuming max size $1 per leg -> $2 per full arb
        return math.floor(self.available_capital / 2.0)

    def can_enter(self) -> bool:
        """
        Check if we have enough bankroll to open at least one leg ($1.00).
        For dual-entry, we effectively need >= 2.00 for a full arb.
        """
        return self.available_capital >= 2.0

    def deploy_capital(self, amount: float):
        self.deployed_capital += amount
        self.logger.info(f"Bankroll Guard: Deployed ${amount:.2f}. Available: ${self.available_capital:.2f}")

    def release_capital(self, amount: float):
        self.deployed_capital = max(0.0, self.deployed_capital - amount)
        self.logger.info(f"Bankroll Guard: Released ${amount:.2f}. Available: ${self.available_capital:.2f}")

    def record_pnl(self, realized_pnl: float):
        self.initial_bankroll += realized_pnl
        self.logger.info(f"Bankroll Guard: Recorded PnL: ${realized_pnl:.2f}. New Total Bankroll: ${self.initial_bankroll:.2f}")
