import os,asyncio,time
from datetime import datetime,timezone
from strategy.strategy import analyze
from cloud.metaapi_adapter import MetaApiAdapter

class TradingEngine:
    def __init__(self):
        self.running=False; self.symbol=os.getenv('DEFAULT_SYMBOL','XAUUSD'); self.volume=float(os.getenv('DEFAULT_VOLUME','0.01')); self.mode='DEMO'
        self.adapter=None; self.task=None; self.last=None; self.positions_cache=[]; self.history=[]; self.last_trade=0
        self.cooldown=int(os.getenv('COOLDOWN_SECONDS','180')); self.max_positions=int(os.getenv('MAX_OPEN_POSITIONS','1')); self.daily_loss=float(os.getenv('MAX_DAILY_LOSS_PERCENT','2'))
        self.day=datetime.now(timezone.utc).date(); self.day_start_equity=None; self.realized_session=0
    def settings(self,symbol=None,volume=None,mode=None):
        if symbol:self.symbol=symbol
        if volume is not None and volume>0:self.volume=volume
        if mode in ('DEMO','LIVE'):self.mode=mode
    async def start(self):
        if self.running:return
        self.adapter=MetaApiAdapter(); await self.adapter.connect(); self.running=True; self.task=asyncio.create_task(self._loop())
    async def stop(self):
        self.running=False
        if self.task:self.task.cancel(); self.task=None
    async def _loop(self):
        while self.running:
            try:
                m1=await self.adapter.candles(self.symbol,'1m'); m5=await self.adapter.candles(self.symbol,'5m'); m15=await self.adapter.candles(self.symbol,'15m')
                self.last=analyze(self.symbol,m15,m5,m1)
                self.positions_cache=await self.adapter.positions()
                if self.last.eligible and len(self.positions_cache)<self.max_positions and time.time()-self.last_trade>=self.cooldown:
                    await self.execute(self.last)
            except asyncio.CancelledError: break
            except Exception as e:self.last={'error':str(e)}
            await asyncio.sleep(5)
    async def execute(self,a):
        if self.mode!='LIVE' or os.getenv('ENABLE_LIVE','false').lower()!='true':return
        if a.side=='BUY':ticket=await self.adapter.buy(self.symbol,self.volume,a.stop_loss,a.take_profit)
        else:ticket=await self.adapter.sell(self.symbol,self.volume,a.stop_loss,a.take_profit)
        self.last_trade=time.time(); self.history.append({'time':datetime.now(timezone.utc).isoformat(),'symbol':self.symbol,'side':a.side,'volume':self.volume,'score':a.score,'ticket':str(ticket)})
    async def emergency_close(self):
        if self.adapter:await self.adapter.close_all()
    async def account(self):return await self.adapter.account_info() if self.adapter else {'connected':False}
    async def positions(self):return await self.adapter.positions() if self.adapter else []
    async def chart(self):return await self.adapter.candles(self.symbol,'1m',100) if self.adapter else []
    def status(self):
        a=self.last.__dict__ if hasattr(self.last,'__dict__') else self.last
        return {'running':self.running,'mode':self.mode,'symbol':self.symbol,'volume':self.volume,'analysis':a,'history':self.history[-50:]}
