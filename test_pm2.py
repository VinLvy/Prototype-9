import logging
logging.basicConfig(level=logging.ERROR)
from core.price_monitor import PriceMonitor
import asyncio

async def test():
    pm = PriceMonitor(markets=[])
    pm._heartbeat_loop = lambda ws: asyncio.sleep(86400)
    
    stream_task = asyncio.create_task(anext(pm.stream_prices()))
    
    await asyncio.sleep(5)
    print("ALL states:")
    target = 0
    for asset, state in pm._price_state.items():
        if state['best_ask'] > 0:
            print(f"{asset}: {state}")
            target += 1
    
    print(f"Total populated targets: {target}")
    stream_task.cancel()

if __name__ == "__main__":
    asyncio.run(test())
