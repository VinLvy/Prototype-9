import argparse
import asyncio
import logging
import sys
from typing import Optional

# Setup standard logging format outside the dashboard
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Optional dependencies imported gracefully
try:
    from core import (
        PriceMonitor,
        ArbitrageDetector,
        ExecutionEngine,
        RiskManager,
        DataLogger,
        Dashboard
    )
except ImportError as e:
    logging.critical(f"Failed to import core modules: {e}")
    sys.exit(1)


async def main_loop(args: argparse.Namespace):
    """
    Main asynchronous loop of the Prototype-9 application.
    """
    # 1. Initialize core components
    dashboard = Dashboard()
    data_logger = DataLogger(db_path="./data/trades.db")
    risk_manager = RiskManager(
        max_position_usd=args.max_pos,
        daily_loss_limit=30.0, # Could be from settings/args
        max_open_positions=3
    )
    execution_engine = ExecutionEngine(
        mode=args.mode,
        risk_manager=risk_manager,
        data_logger=data_logger
    )
    arb_detector = ArbitrageDetector(
        min_spread_threshold=args.min_spread
    )
    price_monitor = PriceMonitor(
        markets=[args.market] if args.market else [] # Empty means subscribe to all target markets
    )

    # 2. Setup communication queues between components
    price_update_queue = asyncio.Queue()
    execution_signal_queue = asyncio.Queue()

    # 3. Define the pipeline tasks
    async def run_dashboard():
        """Task to continually render the dashboard."""
        await dashboard.render_loop()

    async def ingest_prices():
        """Task to stream prices to the queue."""
        async for price_tick in price_monitor.stream_prices():
            await price_update_queue.put(price_tick)
            # Update Dashboard state logic can be hooked here
            # dashboard.update_market_data(price_tick)

    async def process_arbitrage():
        """Task to consume price updates and detect arbitrage opportunities."""
        while True:
            price_tick = await price_update_queue.get()
            signal = arb_detector.calculate_spread(price_tick)
            if signal:
                await execution_signal_queue.put(signal)
            price_update_queue.task_done()

    async def execute_trades():
        """Task to consume execution signals and place orders."""
        while True:
            signal = await execution_signal_queue.get()
            await execution_engine.execute_arbitrage(signal)
            execution_signal_queue.task_done()

    # 4. Start all tasks concurrently
    tasks = [
        asyncio.create_task(run_dashboard()),
        asyncio.create_task(ingest_prices()),
        asyncio.create_task(process_arbitrage()),
        asyncio.create_task(execute_trades())
    ]

    try:
        logging.info(f"Starting Prototype-9 in {args.mode.upper()} mode...")
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logging.info("Shutting down cleanly...")
    finally:
        # Cleanup routine
        data_logger.close()
        for t in tasks:
            t.cancel()

def main():
    """
    Entry point parser for Prototype-9.
    """
    parser = argparse.ArgumentParser(description="Prototype-9: Polymarket High-Frequency Arbitrage System")
    parser.add_argument(
        "--mode", 
        choices=["paper", "live"], 
        default="paper", 
        help="Trading mode (default: paper)"
    )
    parser.add_argument(
        "--min-spread", 
        type=float, 
        default=0.020, 
        help="Minimum spread threshold to trigger trades (default: 0.020)"
    )
    parser.add_argument(
        "--max-pos", 
        type=float, 
        default=50.0, 
        help="Max position size per trade in USD (default: 50.0)"
    )
    parser.add_argument(
        "--log-level", 
        choices=["DEBUG", "INFO", "WARNING", "ERROR"], 
        default="INFO", 
        help="Logging verbosity level"
    )
    parser.add_argument(
        "--market", 
        type=str, 
        default=None, 
        help="Optional: Run against a specific market only (e.g. BTC-UP-DOWN-15M)"
    )

    args = parser.parse_args()

    # Set logger level based on args
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Run the asyncio event loop
    try:
        asyncio.run(main_loop(args))
    except KeyboardInterrupt:
        logging.info("Interrupted by user. Exiting...")
    except Exception as e:
        logging.critical(f"Fatal error encountered: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
