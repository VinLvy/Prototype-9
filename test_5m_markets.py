import asyncio, aiohttp

async def test():
    async with aiohttp.ClientSession() as s:
        # WITH closed=false (current broken behavior)
        r = await s.get('https://gamma-api.polymarket.com/markets', params={'active':'true','closed':'false','limit':'10'})
        data = await r.json()
        btc5m = [m for m in data if 'updown-5m' in (m.get('slug') or '').lower()]
        print(f'With closed=false: {len(btc5m)} 5m markets found')
        
        # WITHOUT closed filter (fix)
        r2 = await s.get('https://gamma-api.polymarket.com/markets', params={'active':'true','limit':'100'})
        data2 = await r2.json()
        btc5m2 = [m for m in data2 if 'updown-5m' in (m.get('slug') or '').lower()]
        print(f'Without closed filter: {len(btc5m2)} 5m markets found')
        for m in btc5m2[:3]:
            print(f'  → {m.get("slug")} | end: {m.get("endDate")}')

asyncio.run(test())
