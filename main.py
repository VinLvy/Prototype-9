import argparse
import asyncio
import logging
import sys
from typing import Optional

import config.settings as settings

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
        BoneReaperDetector,
        ExecutionEngine,
        RiskManager,
        DataLogger,
        Dashboard
    )
    from core.copy_trade_watcher import CopyTradeWatcher
except ImportError as e:
    logging.critical(f"Failed to import core modules: {e}")
    sys.exit(1)




async def main_loop(args: argparse.Namespace):
    """
    Main asynchronous loop of the Prototype-9 application.
    """
    # 1. Initialize core components
    dashboard = Dashboard()
    dashboard.set_mode(args.mode)
    
    if args.strategy == "bonereaper":
        db_file = "./data/bonereaper_trades.db"
    elif args.strategy == "copytrade":
        db_file = "./data/copytrade_trades.db"
    else:
        db_file = "./data/trades.db"
    data_logger = DataLogger(db_path=db_file)
    
    risk_manager = RiskManager(
        max_position_usd=args.max_pos,
        daily_loss_limit=30.0,
        max_open_positions=100
    )
    execution_engine = ExecutionEngine(
        mode=args.mode,
        risk_manager=risk_manager,
        data_logger=data_logger
    )
    if args.strategy == "bonereaper":
        detector = BoneReaperDetector(risk_manager=risk_manager)
    elif args.strategy == "copytrade":
        target_wallet = args.target_wallet or settings.TARGET_WALLET
        if not target_wallet:
            logging.critical("copytrade strategy requires --target-wallet or TARGET_WALLET in .env")
            sys.exit(1)
        detector = None  # Copy trade uses CopyTradeWatcher directly
        copy_watcher = CopyTradeWatcher(target_wallet=target_wallet)
    else:
        detector = ArbitrageDetector(
            min_spread_threshold=args.min_spread,
            risk_manager=risk_manager
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
            
            if price_tick.get("event") == "MARKET_RESOLVED":
                market_id = price_tick["market_id"]
                risk_manager.clear_position(market_id, pnl=0.0)
                
                if hasattr(detector, 'market_states'):
                    state = detector.market_states.pop(market_id, None)
                    if state and state.get("state") == "ENTERED":
                        estimated_entry_cost = state.get("entry_price", 0.0) * args.max_pos
                        dashboard.record_execution({
                            "market_id": market_id,
                            "mode": args.mode,
                            "status": "LOSS",
                            "spread": 0.0,
                            "estimated_profit": -estimated_entry_cost
                        })
                price_update_queue.task_done()
                continue

            if args.strategy == "bonereaper":
                signal = detector.calculate_signal(price_tick)
            elif args.strategy == "copytrade":
                # copytrade doesn't use price_update_queue for detection
                price_update_queue.task_done()
                continue
            else:
                signal = detector.calculate_spread(price_tick)
                
            if signal:
                dashboard.record_opportunity(signal)
                await execution_signal_queue.put(signal)
            price_update_queue.task_done()

    async def run_copy_trade():
        """Task for copy trade: watches target wallet and queues signals."""
        if args.strategy != "copytrade":
            return
        async for signal in copy_watcher.watch():
            dashboard.record_opportunity(signal)
            await execution_signal_queue.put(signal)

    async def execute_trades():
        """Task to consume execution signals and place orders."""
        paper_trade_count = 0
        while True:
            signal = await execution_signal_queue.get()
            trade_record = await execution_engine.execute_arbitrage(signal)
            if trade_record:
                dashboard.record_execution(trade_record)
            execution_signal_queue.task_done()

    # 4. Start all tasks concurrently
    tasks = [
        asyncio.create_task(run_dashboard()),
        asyncio.create_task(ingest_prices()),
        asyncio.create_task(process_arbitrage()),
        asyncio.create_task(execute_trades()),
        asyncio.create_task(run_copy_trade()),
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
        default=settings.TRADING_MODE, 
        help=f"Trading mode (default from .env: {settings.TRADING_MODE})"
    )
    parser.add_argument(
        "--min-spread", 
        type=float, 
        default=settings.MIN_SPREAD, 
        help=f"Minimum spread threshold to trigger trades (default from .env: {settings.MIN_SPREAD})"
    )
    parser.add_argument(
        "--strategy", 
        choices=["arb", "bonereaper", "copytrade"], 
        default=settings.STRATEGY, 
        help=f"Trading strategy to use (default from .env: {settings.STRATEGY})"
    )
    parser.add_argument(
        "--target-wallet",
        type=str,
        default=None,
        help="Target wallet address to copy trade (required for --strategy copytrade)"
    )
    parser.add_argument(
        "--max-pos", 
        type=float, 
        default=settings.MAX_POSITION_USD, 
        help=f"Max position size per trade in USD (default from .env: {settings.MAX_POSITION_USD})"
    )
    parser.add_argument(
        "--log-level", 
        choices=["DEBUG", "INFO", "WARNING", "ERROR"], 
        default="WARNING", # Default diubah ke WARNING agar TUI rich Dashboard tidak tertabrak teks log
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
