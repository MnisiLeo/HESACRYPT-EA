import os, asyncio, logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .engine import engine

logging.basicConfig(level=logging.INFO)
app=FastAPI(title="L.Mnisi Cloud Master Scalper",version="3.0")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])

APP_KEY=os.getenv("APP_KEY","")
WEB=Path(__file__).resolve().parent.parent/"web"

def auth(x_app_key):
    if APP_KEY and x_app_key!=APP_KEY: raise HTTPException(401,"Invalid app key.")

class Control(BaseModel):
    action:str

@app.on_event("startup")
async def startup():
    if os.getenv("AUTO_START","false").lower()=="true":
        try: await engine.start()
        except Exception: logging.exception("Auto start failed")

@app.on_event("shutdown")
async def shutdown():
    await engine.stop()

@app.get("/")
async def home(): return FileResponse(WEB/"index.html")

@app.get("/manifest.json")
async def manifest(): return FileResponse(WEB/"manifest.json")

@app.get("/assets/{name}")
async def asset(name:str): return FileResponse(WEB/"assets"/name)

@app.get("/api/health")
async def health():
    return {"ok":True,"phone_only":True,"running":engine.running,"live_enabled":engine.live}

@app.get("/api/status")
async def status(x_app_key:str|None=Header(None)):
    auth(x_app_key); return engine.status()

@app.post("/api/control")
async def control(c:Control,x_app_key:str|None=Header(None)):
    auth(x_app_key)
    if c.action=="start":
        await engine.start(); return {"ok":True}
    if c.action=="stop":
        await engine.stop(); return {"ok":True}
    raise HTTPException(400,"Unknown action")

@app.get("/api/account")
async def account(x_app_key:str|None=Header(None)):
    auth(x_app_key)
    if not engine.conn: return {"connected":False}
    return {"connected":True,"information":await engine.conn.get_account_information()}

@app.get("/api/positions")
async def positions(x_app_key:str|None=Header(None)):
    auth(x_app_key)
    if not engine.conn:return []
    return await engine.conn.get_positions()

@app.get("/api/history")
async def history(x_app_key:str|None=Header(None)):
    auth(x_app_key)
    if not engine.conn:return []
    return list(engine.trade_log)
