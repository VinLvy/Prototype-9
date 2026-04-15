import logging
from typing import Dict, Any, Optional

class ArbitrageDetector:
    """
    ArbitrageDetector listens for price ticks and detects when the sum of
    complimentary markets (YES + NO) exceeds 1.00 + expected fees/threshold.
    """

    def __init__(self, min_spread_threshold: float = 0.020):
        """
        Initialize the detector.

        Args:
            min_spread_threshold (float): Minimum spread percentage to consider an arb valid.
                                          0.02 means 2.0% spread required (e.g. YES+NO > 1.02)
        """
        self.min_spread_threshold = min_spread_threshold
        self.logger = logging.getLogger(self.__class__.__name__)

    def calculate_spread(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Calculates the spread for a given price tick.
        
        Core logic: YES_price + NO_price > 1.00 + gas_fee (mocked) + min_threshold
        
        Args:
            tick (Dict[str, Any]): Dictionary containing 'yes_price', 'no_price', and 'market_id'.
        
        Returns:
            Optional[Dict[str, Any]]: A trading signal dictionary if arbitrage exists, 
                                      or None if no opportunity detected.
        """
        yes_price = tick.get('yes_price', 0.0)
        no_price = tick.get('no_price', 0.0)
        
        # In a real scenario, gas fee estimate is dynamically injected here.
        # For simplicity, we assume the threshold is inclusive of gas buffer,
        # or we mocked gas cost as static. Let's assume a 0.005 fixed gas amortized percentage for now.
        simulated_gas_factor = 0.005 
        
        combined_price = yes_price + no_price
        target_break_even = 1.00 + simulated_gas_factor + self.min_spread_threshold

        if combined_price >= target_break_even:
            spread = combined_price - 1.00
            signal = {
                'market_id': tick.get('market_id'),
                'yes_price': yes_price,
                'no_price': no_price,
                'spread': spread,
                'estimated_profit_per_share': spread - simulated_gas_factor,
                'timestamp': tick.get('timestamp')
            }
            self.logger.info(
                f"Opportunity verified on {signal['market_id']} | "
                f"YES: {yes_price:.2f} NO: {no_price:.2f} | "
                f"Spread: {spread * 100:.2f}%"
            )
            return signal
            
        return None
