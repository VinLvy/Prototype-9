import logging
logging.basicConfig(level=logging.ERROR)
from core.price_monitor import PriceMonitor
import asyncio

async def test():
    pm = PriceMonitor(markets=[])
    
    # Disable heartbeat to see if it stops dropping
    pm._heartbeat_loop = lambda ws: asyncio.sleep(86400)
    
    c = 0
    print("Starting tick stream...")
    async for tick in pm.stream_prices():
        print(f"Tick: {tick['yes_price']} - {tick['no_price']} - {tick['market_id']}")
        c += 1
        if c > 10:
            break

asyncio.run(test())
