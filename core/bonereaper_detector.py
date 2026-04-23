import logging
from typing import Dict, Any, Optional
import time
from datetime import datetime, timezone

import config.settings as settings
from utils.kelly import KellyCriterion

class BoneReaperDetector:
    """
    State machine per market:
    IDLE -> ENTERED -> HEDGED

    Entry rules:
    - Single leg entry when price <= ENTRY_PRICE_THRESHOLD
    - Prefer the LOWER priced side (more upside potential)
    - REJECT entry if the OTHER side price is already >= MAX_COMBINED_COST - entry_price
      (i.e., hedge will be impossible at profit from the start)

    Hedge rules:
    - Trigger after HEDGE_TRIGGER_SECONDS held
    - combined_cost (entry_price + current_other_side) MUST be <= MAX_COMBINED_COST
    - If < 60s to market close and still ENTERED: force CUT_LOSS hedge

    Spread calculation:
    - spread = 1.00 - combined_cost
    - estimated_profit_per_share = spread - GAS_FACTOR (0.005)
    - If combined_cost > 1.00: spread is negative = loss
    """

    GAS_FACTOR = 0.005  # simulated gas cost per share
    SLIPPAGE_BUFFER = 0.03  # 3% untuk low-liquidity 5m markets

    def __init__(self, risk_manager=None):
        self.risk_manager = risk_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        self.entry_threshold = settings.ENTRY_PRICE_THRESHOLD
        self.hedge_trigger_seconds = settings.HEDGE_TRIGGER_SECONDS
        self.max_combined_cost = settings.MAX_COMBINED_COST
        self.max_pos_usd = settings.MAX_POSITION_USD

        self.kelly = KellyCriterion(bankroll=100.0, use_half_kelly=True)

        # State: { market_id: { state, entry_side, entry_price, entry_time } }
        self.market_states = {}

    def calculate_signal(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        market_id = tick.get('market_id')
        yes_price = tick.get('yes_price', 0.0)
        no_price = tick.get('no_price', 0.0)

        if not market_id or not tick.get('yes_token_id') or not tick.get('no_token_id'):
            return None

        if yes_price <= 0.0 or no_price <= 0.0:
            return None

        # GUARD: if combined is already > 1.00, this market has no arb potential at all
        # Skip entirely regardless of state — prices are inverted/abnormal
        if yes_price + no_price > 1.10:
            self.logger.debug(
                f"[{market_id}] Skipped: combined price {yes_price + no_price:.3f} > 1.10 "
                f"(YES={yes_price:.3f}, NO={no_price:.3f}) — no arb possible"
            )
            return None

        current_time = tick.get("timestamp", time.time() * 1000) / 1000.0

        if market_id not in self.market_states:
            self.market_states[market_id] = {
                "state": "IDLE",
                "entry_side": None,
                "entry_price": 0.0,
                "entry_time": 0.0
            }

        state = self.market_states[market_id]

        # Compute time to close
        end_date_iso = tick.get("end_date_iso")
        time_to_close_seconds = float('inf')
        if end_date_iso:
            try:
                end_dt = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
                now_utc = datetime.now(timezone.utc)
                time_to_close_seconds = (end_dt - now_utc).total_seconds()
            except Exception:
                pass

        # --- Hard Cut Loss: < 60s to close, still single-legged ---
        if time_to_close_seconds <= 60 and state["state"] == "ENTERED":
            hedge_side = "NO" if state["entry_side"] == "YES" else "YES"
            hedge_price = no_price if hedge_side == "NO" else yes_price
            combined_cost = state["entry_price"] + hedge_price
            spread = 1.00 - combined_cost
            estimated_profit = spread - self.GAS_FACTOR  # likely negative = loss

            self.logger.warning(
                f"[{market_id}] CUT_LOSS: {time_to_close_seconds:.0f}s left. "
                f"Combined={combined_cost:.3f}, spread={spread:.3f}"
            )
            self.market_states[market_id]["state"] = "HEDGED"

            signal = self._create_signal(tick, hedge_side, hedge_price, reason="CUT_LOSS")
            signal["entry_price"] = state["entry_price"]
            signal["spread"] = spread
            signal["estimated_profit_per_share"] = estimated_profit
            return signal

        # --- Too late to enter ---
        if end_date_iso and state["state"] == "IDLE":
            try:
                end_dt = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
                now_utc = datetime.now(timezone.utc)
                remaining = (end_dt - now_utc).total_seconds()
                if remaining < (self.hedge_trigger_seconds + 90):
                    return None
            except Exception:
                pass

        # --- ENTRY ---
        if state["state"] == "IDLE":
            # Pick the cheaper side
            target_side = "YES" if yes_price < no_price else "NO"
            target_price = yes_price if target_side == "YES" else no_price
            other_price = no_price if target_side == "YES" else yes_price

            if target_price > self.entry_threshold:
                self.logger.debug(
                    f"[{market_id}] Skipped Entry: {target_side}={target_price:.3f} "
                    f"> threshold {self.entry_threshold}"
                )
                return None

            # CRITICAL CHECK: verify hedge is POSSIBLE at profit from current prices
            # If other side is already too expensive, entering guarantees a loss
            best_case_combined = target_price + other_price
            if best_case_combined > (self.max_combined_cost - self.SLIPPAGE_BUFFER):
                self.logger.debug(
                    f"[{market_id}] Skipped Entry: best-case combined "
                    f"{best_case_combined:.3f} > MAX_COMBINED_COST - SLIPPAGE {self.max_combined_cost - self.SLIPPAGE_BUFFER:.3f} "
                    f"— hedge impossible at profit"
                )
                return None

            self.market_states[market_id].update({
                "state": "ENTERED",
                "entry_side": target_side,
                "entry_price": target_price,
                "entry_time": current_time
            })

            # Kelly sizing
            win_prob = 1.0 - target_price
            profit_on_win = (1.00 - target_price) / target_price if target_price > 0 else 0
            kelly_size = self.kelly.compute(
                win_prob,
                profit_on_win,
                loss_on_loss=1.0,
                max_position_usd=self.max_pos_usd
            )

            # Projected profit if hedge achieved at current other_price
            projected_combined = target_price + other_price
            projected_spread = 1.00 - projected_combined
            projected_profit = projected_spread - self.GAS_FACTOR

            signal = self._create_signal(tick, target_side, target_price, reason="ENTRY", size_usd=kelly_size)
            # Note: ENTRY profit is PROJECTED, not realized. Mark clearly.
            signal["spread"] = projected_spread
            signal["estimated_profit_per_share"] = projected_profit
            return signal

        # --- HEDGE ---
        elif state["state"] == "ENTERED":
            time_held = current_time - state["entry_time"]
            entry_cost = state["entry_price"]

            if time_held <= self.hedge_trigger_seconds:
                self.logger.debug(
                    f"[{market_id}] Waiting to hedge: {time_held:.1f}s / {self.hedge_trigger_seconds}s"
                )
                return None

            hedge_side = "NO" if state["entry_side"] == "YES" else "YES"
            current_other_price = no_price if hedge_side == "NO" else yes_price
            combined_cost = entry_cost + current_other_price

            if combined_cost > (self.max_combined_cost - self.SLIPPAGE_BUFFER):
                self.logger.debug(
                    f"[{market_id}] Hedge rejected: combined {combined_cost:.3f} "
                    f"> max {self.max_combined_cost - self.SLIPPAGE_BUFFER:.3f} (incl. slippage buffer)"
                )
                return None

            # Valid hedge
            spread = 1.00 - combined_cost
            estimated_profit = spread - self.GAS_FACTOR  # could be negative if spread < gas

            self.market_states[market_id]["state"] = "HEDGED"

            self.logger.info(
                f"[{market_id}] HEDGE signal: {hedge_side} @ {current_other_price:.3f} | "
                f"Entry={entry_cost:.3f} | Combined={combined_cost:.3f} | "
                f"Spread={spread:.3f} | Est.Profit/share={estimated_profit:.4f}"
            )

            signal = self._create_signal(tick, hedge_side, current_other_price, reason="HEDGE")
            signal["entry_price"] = entry_cost
            signal["spread"] = spread
            signal["estimated_profit_per_share"] = estimated_profit
            return signal

        return None

    def _create_signal(
        self,
        tick: Dict[str, Any],
        side: str,
        execution_price: float,
        reason: str,
        size_usd: float = 1.0
    ) -> Dict[str, Any]:
        return {
            'market_id': tick.get('market_id'),
            'condition_id': tick.get('condition_id'),
            'yes_token_id': tick.get('yes_token_id'),
            'no_token_id': tick.get('no_token_id'),
            'side': side,
            'execution_price': execution_price,
            'yes_price': tick.get('yes_price'),
            'no_price': tick.get('no_price'),
            'timestamp': tick.get('timestamp'),
            'end_date_iso': tick.get('end_date_iso'),
            'reason': reason,
            'recommended_size_usd': size_usd,
            'spread': 0.0,
            'estimated_profit_per_share': 0.0
        }