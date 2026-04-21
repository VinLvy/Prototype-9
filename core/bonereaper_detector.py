import logging
from typing import Dict, Any, Optional
import time
from datetime import datetime, timezone

import config.settings as settings
from utils.kelly import KellyCriterion

class BoneReaperDetector:
    """
    State machine per market:
    IDLE -> ENTERED_ONE_SIDE -> HEDGED (both sides held) -> RESOLVED
    
    Entry rules:
    - Only 5-min markets (end_date_iso within 5 minutes of market open)
    - Single leg entry when price <= ENTRY_PRICE_THRESHOLD (default: 0.35)
    - Prefer the side with LOWER price (more upside)
    
    Hedge rules:  
    - Trigger hedge if: time_held > HEDGE_TRIGGER_SECONDS (default: 120)
      AND combined_cost (entry_price + current_other_side) <= 0.97
    - If hedge not achievable within 60s of market close, EXIT single leg
      at market price (cut loss)
    
    Sizing: Uses Kelly Criterion with win_probability derived from 
    implied market odds (1 - current_price of winning side)
    """

    def __init__(self, risk_manager=None):
        self.risk_manager = risk_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        self.entry_threshold = settings.ENTRY_PRICE_THRESHOLD
        self.hedge_trigger_seconds = settings.HEDGE_TRIGGER_SECONDS
        self.max_combined_cost = settings.MAX_COMBINED_COST
        
        # Paper mode sizing limits
        self.max_pos_usd = settings.MAX_POSITION_USD
        
        # Kelly initialized with $100 arbitrary bankroll for sizing calculation
        self.kelly = KellyCriterion(bankroll=100.0, use_half_kelly=True)
        
        # State tracking: { market_id: { "state", "entry_side", "entry_price", "entry_time" } }
        self.market_states = {}

    def calculate_signal(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        market_id = tick.get('market_id')
        yes_price = tick.get('yes_price', 0.0)
        no_price = tick.get('no_price', 0.0)
        
        if not market_id or not tick.get('yes_token_id') or not tick.get('no_token_id'):
            return None
            
        if yes_price <= 0.0 or no_price <= 0.0:
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
        
        # 1. Check Hard Cut Loss (60s to close)
        end_date_iso = tick.get("end_date_iso")
        time_to_close_seconds = float('inf')
        if end_date_iso:
            try:
                end_dt = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
                # Current time as aware UTC datetime
                now_utc = datetime.now(timezone.utc)
                time_to_close_seconds = (end_dt - now_utc).total_seconds()
            except Exception as e:
                pass

        if time_to_close_seconds <= 60 and state["state"] == "ENTERED":
            self.logger.warning(f"[{market_id}] < 60s to close. Forcing cut-loss hedge.")
            hedge_side = "NO" if state["entry_side"] == "YES" else "YES"
            hedge_price = no_price if hedge_side == "NO" else yes_price
            
            self.market_states[market_id]["state"] = "HEDGED"
            return self._create_signal(tick, hedge_side, hedge_price, reason="CUT_LOSS")

        # Check if too late to enter
        if end_date_iso and state["state"] == "IDLE":
            try:
                end_dt = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
                now_utc = datetime.now(timezone.utc)
                remaining = (end_dt - now_utc).total_seconds()
                if remaining < 90:
                    return None  # Terlalu terlambat untuk entry
            except Exception:
                pass

        # 2. Check Entry
        if state["state"] == "IDLE":
            target_side = "YES" if yes_price < no_price else "NO"
            target_price = yes_price if target_side == "YES" else no_price
            
            if target_price <= self.entry_threshold:
                self.market_states[market_id].update({
                    "state": "ENTERED",
                    "entry_side": target_side,
                    "entry_price": target_price,
                    "entry_time": current_time
                })
                
                # Kelly Sizing
                win_prob = 1.0 - target_price
                # Profit on win for buying a leg is 1.00 - target_price (net profit)
                # But here we pass exactly what Kelly needs: 1.00 payout / cost => (1-cost)/cost
                profit_on_win = (1.00 - target_price) / target_price if target_price > 0 else 0
                loss_on_loss = 1.0  # Lose entire stake
                
                kelly_size = self.kelly.compute(
                    win_prob, 
                    profit_on_win, 
                    loss_on_loss, 
                    max_position_usd=self.max_pos_usd
                )
                
                return self._create_signal(
                    tick, target_side, target_price, 
                    reason="ENTRY", size_usd=kelly_size
                )
            else:
                self.logger.debug(f"[{market_id}] Skipped Entry: Lowest price {target_price} > {self.entry_threshold}")
                
        # 3. Check Hedge
        elif state["state"] == "ENTERED":
            time_held = current_time - state["entry_time"]
            entry_cost = state["entry_price"]
            
            if time_held > self.hedge_trigger_seconds:
                hedge_side = "NO" if state["entry_side"] == "YES" else "YES"
                current_other_side = no_price if hedge_side == "NO" else yes_price
                combined_cost = entry_cost + current_other_side
                
                if combined_cost <= self.max_combined_cost:
                    self.market_states[market_id]["state"] = "HEDGED"
                    
                    spread = 1.00 - combined_cost
                    signal = self._create_signal(tick, hedge_side, current_other_side, reason="HEDGE")
                    signal["spread"] = spread
                    signal["estimated_profit_per_share"] = spread - 0.005 # simulated gas baseline
                    return signal
                else:
                    self.logger.debug(f"[{market_id}] Skipped Hedge: Combined cost {combined_cost:.3f} > {self.max_combined_cost}")
            else:
                # Log explicitly per rules "Log every signal evaluation"
                self.logger.debug(f"[{market_id}] Skipped Hedge: time held {time_held:.1f}s <= {self.hedge_trigger_seconds}s")

        return None

    def _create_signal(self, tick: Dict[str, Any], side: str, execution_price: float, reason: str, size_usd: float = 1.0) -> Dict[str, Any]:
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
            'reason': reason,
            'recommended_size_usd': size_usd,
            'spread': 0.0, 
            'estimated_profit_per_share': 0.0
        }
