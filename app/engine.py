import os, asyncio, time, uuid, logging
from datetime import datetime, timezone
from collections import defaultdict, deque
from metaapi_cloud_sdk import MetaApi
from .strategy import analyze

log=logging.getLogger("lmnisiengine")

class Engine:
    def __init__(self):
        self.token=os.getenv("METAAPI_TOKEN","")
        self.account_id=os.getenv("METAAPI_ACCOUNT_ID","")
        self.live=os.getenv("ENABLE_LIVE","false").lower()=="true"
        self.symbols=[x.strip() for x in os.getenv("SYMBOLS","XAUUSD").split(",") if x.strip()]
        self.default_volume=float(os.getenv("DEFAULT_VOLUME","0.01"))
        self.max_positions=int(os.getenv("MAX_OPEN_POSITIONS","1"))
        self.max_daily_loss=float(os.getenv("MAX_DAILY_LOSS_PERCENT","3"))
        self.cooldown=int(os.getenv("COOLDOWN_SECONDS","180"))
        self.rr=float(os.getenv("RISK_REWARD","2"))
        self.running=False
        self.api=None; self.account=None; self.conn=None
        self.candles=defaultdict(lambda: defaultdict(lambda: deque(maxlen=400)))
        self.latest={}
        self.last_trade=0
        self.last_result={}
        self.trade_log=deque(maxlen=100)
        self._task=None

    async def start(self):
        if self.running:return
        if not self.token or not self.account_id:
            raise RuntimeError("METAAPI_TOKEN and METAAPI_ACCOUNT_ID are required.")
        self.running=True
        self.api=MetaApi(self.token)
        self.account=await self.api.metatrader_account_api.get_account(self.account_id)
        if self.account.state!="DEPLOYED": await self.account.deploy()
        if self.account.connection_status!="CONNECTED": await self.account.wait_connected()
        self.conn=self.account.get_streaming_connection()
        await self.conn.connect()
        await self.conn.wait_synchronized()
        for s in self.symbols:
            await self._seed(s)
            await self.conn.subscribe_to_market_data(s,[
                {"type":"quotes","intervalInMilliseconds":1000},
                {"type":"candles","timeframe":"1m","intervalInMilliseconds":1000},
                {"type":"candles","timeframe":"5m","intervalInMilliseconds":5000},
                {"type":"candles","timeframe":"15m","intervalInMilliseconds":15000}
            ])
        self._task=asyncio.create_task(self._loop())
        log.info("L.Mnisi engine running")

    async def _seed(self,s):
        # Historical market-data REST endpoint via the account helper where supported.
        # Use SDK RPC historical candles first; if unavailable, fall back to direct REST.
        for tf in ("1m","5m","15m"):
            try:
                cs=await self.account.get_historical_candles(symbol=s,timeframe=tf,start_time=None,limit=300)
                for c in cs:
                    self.candles[s][tf].append(c)
            except Exception as e:
                log.warning("Historical seed %s %s: %s",s,tf,e)

    async def stop(self):
        self.running=False
        if self._task:
            self._task.cancel()
            self._task=None
        if self.conn:
            try: await self.conn.close()
            except Exception: pass
        if self.api:
            try: await self.api.close()
            except Exception: pass
        self.conn=self.account=self.api=None

    def feed(self,c):
        s=c.get("symbol"); tf=c.get("timeframe")
        if s and tf in ("1m","5m","15m"):
            q=self.candles[s][tf]
            if q and q[-1]["time"]==c["time"]: q[-1]=c
            else:q.append(c)

    async def _loop(self):
        # The cloud worker stays alive and evaluates closed candles.
        while self.running:
            try:
                for s in self.symbols:
                    r=self.evaluate(s)
                    self.latest[s]=r
                    if r.get("eligible"): await self.maybe_trade(s,r)
            except Exception as e: log.exception("engine loop: %s",e)
            await asyncio.sleep(2)

    def evaluate(self,s):
        m1=list(self.candles[s]["1m"]);m5=list(self.candles[s]["5m"]);m15=list(self.candles[s]["15m"])
        if min(len(m1),len(m5),len(m15))<40:return {"eligible":False,"score":0,"reason":"Loading market data","symbol":s}
        r=analyze(m1[:-1],m5[:-1],m15[:-1]);r["symbol"]=s
        return r

    async def maybe_trade(self,s,r):
        if not self.live:return
        if time.time()-self.last_trade<self.cooldown:return
        positions=await self.conn.get_positions()
        if len(positions)>=self.max_positions:return
        # Do not duplicate an existing position on the same symbol.
        if any(p.get("symbol")==s for p in positions):return
        volume=self.default_volume
        cid=f"LMNISI_{s}_{uuid.uuid4().hex[:12]}"
        if r["direction"]=="BUY":
            res=await self.conn.create_market_buy_order(s,volume,r["stop"],r["target"],{"comment":"L.Mnisi 17/22","clientId":cid})
        else:
            res=await self.conn.create_market_sell_order(s,volume,r["stop"],r["target"],{"comment":"L.Mnisi 17/22","clientId":cid})
        self.last_trade=time.time()
        entry={"time":datetime.now(timezone.utc).isoformat(),"symbol":s,"direction":r["direction"],"score":r["score"],"result":res}
        self.trade_log.appendleft(entry)

    def status(self):
        return {"running":self.running,"live_enabled":self.live,"symbols":self.symbols,
                "account_connected":bool(self.conn),"latest":self.latest,
                "trades":list(self.trade_log)}

engine=Engine()
