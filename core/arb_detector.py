import logging
from typing import Dict, Any, Optional

class ArbitrageDetector:
    """
    ArbitrageDetector listens for price ticks and detects asymmetric opportunities.
    It triggers independent leg buying (YES or NO) based on dynamically calculated
    fair value targets to keep the combined cost < 1.00 - gas - min_spread.
    """

    def __init__(self, min_spread_threshold: float = 0.020, risk_manager=None):
        """
        Initialize the detector.

        Args:
            min_spread_threshold (float): Minimum spread percentage to consider an arb valid.
            risk_manager (RiskManager, optional): Tracks current leg exposure.
        """
        self.min_spread_threshold = min_spread_threshold
        self.risk_manager = risk_manager
        self.logger = logging.getLogger(self.__class__.__name__)

    def calculate_spread(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Calculates asymmetric entry signals.
        """
        yes_price = tick.get('yes_price', 0.0)
        no_price = tick.get('no_price', 0.0)
        market_id = tick.get('market_id')
        
        # 1. Validasi token ID ada dan valid sebagai perlindungan dasar
        if not tick.get('yes_token_id') or not tick.get('no_token_id'):
            return None
            
        # 2. Tolak harga nol atau harga invalid lainnya
        if yes_price <= 0.0 or no_price <= 0.0:
            return None
            
        simulated_gas_factor = 0.005 
        
        # Taker BUY Arbitrage:
        # Keuntungan statis kontrak berakhir = 1.00
        # Validasi profit: 1.00 - (combined_price) > gas + min_spread
        # Artinya batas maksimum cost (target_max_cost) adalah:
        target_max_cost = 1.00 - simulated_gas_factor - self.min_spread_threshold
        
        # Determine current holdings from RiskManager
        current_pos = {"yes_exposure": 0.0, "no_exposure": 0.0, "yes_price": 0.0, "no_price": 0.0}
        if self.risk_manager:
            current_pos = self.risk_manager.get_position(market_id)
            
        signal = None
        
        # Scenario 1: Hold Nothing. Buy the leg that drops significantly.
        # Simple fair value rule: target_max_cost / 2
        if current_pos["yes_exposure"] == 0 and current_pos["no_exposure"] == 0:
            fair_value = target_max_cost / 2.0
            if yes_price <= fair_value:
                # signal to buy YES
                signal = self._create_signal(tick, "YES", yes_price)
            elif no_price <= fair_value:
                # signal to buy NO
                signal = self._create_signal(tick, "NO", no_price)
                
            # Allow fallback to immediate dual-leg completion if both are cheap enough
            elif (yes_price + no_price) <= target_max_cost:
                 # Standard simultaneous arbitrage
                 signal = self._create_signal(tick, "DUAL", 0.0) # execution_engine might need to handle DUAL
                 # But since we use asymmetric, we can just signal YES first, NO will be picked up next tick.
                 signal = self._create_signal(tick, "YES", yes_price) 
                
        # Scenario 2: Hold YES. We need to buy NO to hedge.
        elif current_pos["yes_exposure"] > 0 and current_pos["no_exposure"] == 0:
            dynamic_no_target = target_max_cost - current_pos["yes_price"]
            if no_price <= dynamic_no_target:
                signal = self._create_signal(tick, "NO", no_price)
                combined_price = current_pos["yes_price"] + no_price
                signal["spread"] = 1.00 - combined_price
                signal["estimated_profit_per_share"] = signal["spread"] - simulated_gas_factor
                
        # Scenario 3: Hold NO. We need to buy YES to hedge.
        elif current_pos["no_exposure"] > 0 and current_pos["yes_exposure"] == 0:
            dynamic_yes_target = target_max_cost - current_pos["no_price"]
            if yes_price <= dynamic_yes_target:
                signal = self._create_signal(tick, "YES", yes_price)
                combined_price = current_pos["no_price"] + yes_price
                signal["spread"] = 1.00 - combined_price
                signal["estimated_profit_per_share"] = signal["spread"] - simulated_gas_factor

        if signal:
            self.logger.info(
                f"Asymmetric Arb verified on {str(market_id)[:30]}... | "
                f"Side: {signal['side']} @ {signal['execution_price']:.3f}"
            )
            return signal
            
        return None

    def _create_signal(self, tick: Dict[str, Any], side: str, execution_price: float) -> Dict[str, Any]:
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
            # Defaults for partial logs:
            'spread': 0.0, 
            'estimated_profit_per_share': 0.0
        }
