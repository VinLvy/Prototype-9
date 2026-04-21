import asyncio, aiohttp, json

async def check():
    async with aiohttp.ClientSession() as s:
        r = await s.get('https://gamma-api.polymarket.com/markets',
                        params={'active':'true','limit':'20'})
        data = await r.json()
    
    import re
    regex = re.compile(r'btc-updown-5m', re.I)
    for m in data:
        if regex.search(m.get('slug','')):
            print('slug    :', m.get('slug'))
            print('question:', m.get('question'))
            print('endDate :', m.get('endDate'))
            print('startDate:', m.get('startDate'))
            try:
                ids = json.loads(m.get('clobTokenIds','[]'))
                print('tokenIds:', ids[0][:20], '...', ids[1][:20])
            except: pass
            print('---')

asyncio.run(check())
