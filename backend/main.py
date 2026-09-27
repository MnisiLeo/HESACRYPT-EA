import os
from pathlib import Path
from fastapi import FastAPI,Header,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from trading_engine.engine import Engine

app=FastAPI(title="L.Mnisi EA API")
engine=Engine(); ROOT=Path(__file__).resolve().parent
KEY=os.getenv("LMNISI_API_KEY","")
def auth(x_api_key):
    if KEY and x_api_key!=KEY: raise HTTPException(401,"Invalid API key")
class Action(BaseModel):
    action:str
    mode:str|None=None

@app.get("/")
def home(): return FileResponse(ROOT.parent/"frontend/index.html")
@app.get("/api/health")
def health(): return {"ok":True,"service":"LMnisi","ready":engine.api.ready()}
@app.get("/api/status")
def status(x_api_key:str|None=Header(None)):
    auth(x_api_key)
    acct={}
    if engine.api.ready():
        try:acct=engine.api.account()
        except Exception as e: engine.log.append("Account: "+str(e))
    r=engine.last
    positions=[]
    if engine.api.ready():
        try:positions=engine.api.positions()
        except:pass
    return {"connected":engine.api.ready(),"running":engine.running,"mode":engine.mode,"symbol":engine.symbol,
            "balance":acct.get("balance"),"equity":acct.get("equity"),"score":getattr(r,"score",0),
            "signal":getattr(r,"side","WAIT"),"reason":getattr(r,"reason","Waiting"),
            "bias":getattr(r,"bias",False),"sweep":getattr(r,"sweep",False),"mss":getattr(r,"mss",False),
            "engulfing":getattr(r,"engulfing",False),"stoch":getattr(r,"stoch",False),
            "displacement":getattr(r,"displacement",False),"positions":positions,"log":engine.log[-30:]}
@app.post("/api/control")
def control(a:Action,x_api_key:str|None=Header(None)):
    auth(x_api_key)
    if a.action=="start":engine.start()
    elif a.action=="stop":engine.stop()
    elif a.action=="mode":
        if a.mode not in ("demo","live"): raise HTTPException(400,"mode must be demo or live")
        engine.mode=a.mode
    return {"ok":True,"running":engine.running,"mode":engine.mode}
@app.post("/api/close-all")
def close_all(x_api_key:str|None=Header(None)):
    auth(x_api_key)
    if not engine.api.ready(): return {"ok":False,"message":"MetaApi not configured"}
    positions=engine.api.positions();out=[]
    for p in positions:
        try:out.append(engine.api.close_position(p["id"]))
        except Exception as e:out.append({"error":str(e),"id":p.get("id")})
    return {"ok":True,"closed":out}
