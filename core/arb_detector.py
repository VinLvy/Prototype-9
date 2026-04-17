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
        
        # 1. Validasi token ID ada dan valid sebagai perlindungan dasar
        if not tick.get('yes_token_id') or not tick.get('no_token_id'):
            return None
            
        # 2. Tolak harga nol atau harga invalid lainnya
        if yes_price <= 0.0 or no_price <= 0.0:
            return None
            
        combined_price = yes_price + no_price
        
        # In a real scenario, gas fee estimate is dynamically injected here.
        simulated_gas_factor = 0.005 
        
        # Taker BUY Arbitrage: Kita Beli YES & Beli NO secara bersamaan.
        # Total cost (modal) = combined_price
        # Keuntungan statis kontrak berakhir = 1.00
        # Agar profit, cost harus < 1.00. 
        # Validasi profit: 1.00 - (combined_price) > gas + min_spread
        # Artinya batas maksimum cost (target_max_cost) adalah:
        target_max_cost = 1.00 - simulated_gas_factor - self.min_spread_threshold

        if combined_price <= target_max_cost:
            # Kotor keuntungan per kontrak
            spread = 1.00 - combined_price 
            signal = {
                'market_id': tick.get('market_id'),
                'condition_id': tick.get('condition_id'),
                'yes_token_id': tick.get('yes_token_id'),
                'no_token_id': tick.get('no_token_id'),
                'yes_price': yes_price,
                'no_price': no_price,
                'spread': spread,
                'estimated_profit_per_share': spread - simulated_gas_factor,
                'timestamp': tick.get('timestamp')
            }
            self.logger.info(
                f"Opportunity verified on {signal['market_id'][:30]}... | "
                f"YES: {yes_price:.3f} NO: {no_price:.3f} | "
                f"Spread: {spread * 100:.2f}%"
            )
            return signal
            
        return None
