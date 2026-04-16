"""
Kelly Criterion Calculator
--------------------------
Computes optimal position size for an arbitrage opportunity.
For spread arbitrage (near-guaranteed), win probability is high but
we still apply half-Kelly as a safety margin.

Formula:
    f* = (b*p - q) / b
    where:
        p = probability of winning
        q = 1 - p (probability of losing)
        b = net odds (profit per unit risked)

Half-Kelly: f_half = f* / 2  (standard conservative application)
"""

import logging
from typing import Optional


class KellyCriterion:
    """
    Computes the optimal fraction of bankroll to deploy per trade
    using the Half-Kelly Criterion.
    """

    def __init__(self, bankroll: float, use_half_kelly: bool = True):
        """
        Args:
            bankroll (float): Total available capital in USD.
            use_half_kelly (bool): If True, apply 50% fraction of full Kelly.
        """
        self.bankroll = bankroll
        self.use_half_kelly = use_half_kelly
        self.logger = logging.getLogger(self.__class__.__name__)

    def compute(
        self,
        win_probability: float,
        profit_on_win: float,
        loss_on_loss: float,
        max_position_usd: Optional[float] = None,
    ) -> float:
        """
        Compute the recommended position size in USD.

        Args:
            win_probability (float): Estimated probability of winning (0.0 – 1.0).
            profit_on_win (float): Net profit per $1 risked if trade wins (e.g. spread %).
            loss_on_loss (float): Net loss per $1 risked if trade loses (e.g. 1.0 = full loss).
            max_position_usd (float, optional): Hard cap. Overrides Kelly if Kelly > cap.

        Returns:
            float: Recommended position size in USD.
        """
        if not (0 < win_probability < 1):
            self.logger.warning(
                f"Invalid win_probability={win_probability}. Must be in (0,1). Returning 0."
            )
            return 0.0

        if profit_on_win <= 0 or loss_on_loss <= 0:
            self.logger.warning("profit_on_win and loss_on_loss must be positive.")
            return 0.0

        loss_probability = 1.0 - win_probability

        # Standard Kelly fraction
        kelly_fraction = (
            (profit_on_win * win_probability) - loss_probability
        ) / profit_on_win

        if kelly_fraction <= 0:
            self.logger.info("Kelly fraction <= 0: no edge detected, skipping trade.")
            return 0.0

        if self.use_half_kelly:
            kelly_fraction /= 2.0

        position_usd = self.bankroll * kelly_fraction

        # Apply hard cap if provided
        if max_position_usd is not None:
            position_usd = min(position_usd, max_position_usd)

        self.logger.debug(
            f"Kelly fraction={kelly_fraction:.4f} | "
            f"Bankroll=${self.bankroll:.2f} | "
            f"Recommended size=${position_usd:.2f}"
        )
        return round(position_usd, 2)

    def update_bankroll(self, new_bankroll: float):
        """Update the bankroll after a trade resolves."""
        self.bankroll = new_bankroll
        self.logger.info(f"Bankroll updated to ${self.bankroll:.2f}")
