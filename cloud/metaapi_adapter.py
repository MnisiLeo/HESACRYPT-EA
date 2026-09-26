import os
try:
    from metaapi_cloud_sdk import MetaApi
except Exception:
    MetaApi=None
class MetaApiAdapter:
    def __init__(self): self.api=self.account=self.connection=None
    async def connect(self):
        if MetaApi is None: raise RuntimeError('metaapi-cloud-sdk unavailable')
        token=os.getenv('METAAPI_TOKEN'); aid=os.getenv('METAAPI_ACCOUNT_ID')
        if not token or not aid: raise RuntimeError('METAAPI_TOKEN and METAAPI_ACCOUNT_ID are required')
        self.api=MetaApi(token); self.account=await self.api.metatrader_account_api.get_account(aid)
        if self.account.state not in ('DEPLOYING','DEPLOYED'): await self.account.deploy()
        await self.account.wait_connected(); self.connection=self.account.get_streaming_connection()
        await self.connection.connect(); await self.connection.wait_synchronized(); return self
    async def candles(self,symbol,tf,limit=300):
        data=await self.account.get_historical_candles(symbol=symbol,timeframe=tf,start_time=None,limit=limit)
        return [{'time':x.get('time'),'open':x['open'],'high':x['high'],'low':x['low'],'close':x['close'],'volume':x.get('volume',0)} for x in data]
    async def account_info(self): return await self.connection.get_account_information()
    async def positions(self): return await self.connection.get_positions()
    async def close_all(self):
        for p in await self.connection.get_positions():
            try: await self.connection.close_position(p['id'])
            except Exception: pass
    async def buy(self,symbol,volume,sl,tp): return await self.connection.create_market_buy_order(symbol,volume,sl,tp,{'comment':'LMnisi-17of22','clientId':'LMnisi'})
    async def sell(self,symbol,volume,sl,tp): return await self.connection.create_market_sell_order(symbol,volume,sl,tp,{'comment':'LMnisi-17of22','clientId':'LMnisi'})
