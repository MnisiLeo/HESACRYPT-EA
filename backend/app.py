from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List
from strategy import analyze

app = FastAPI(title="Phone MT5 Strategy API", version="1.0.0")

class Candle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0

class AnalyzeRequest(BaseModel):
    symbol: str = "XAUUSD"
    m1: List[Candle]
    m5: List[Candle]
    m15: List[Candle]

class OrderRequest(BaseModel):
    symbol: str
    direction: str
    lot_size: float = Field(gt=0)
    sl: float | None = None
    tp: float | None = None
    score: int
    demo: bool = True

@app.get("/health")
def health():
    return {"ok": True, "service": "phone-mt5-strategy", "mode": "DEMO"}

@app.post("/analyze")
def do_analyze(req: AnalyzeRequest):
    result = analyze([x.model_dump() for x in req.m1],
                     [x.model_dump() for x in req.m5],
                     [x.model_dump() for x in req.m15])
    result["symbol"] = req.symbol
    return result

@app.post("/order")
def order(req: OrderRequest):
    if req.score < 17:
        raise HTTPException(400, "Order rejected: score below 17/22")
    if not req.demo:
        raise HTTPException(403, "Live execution is disabled in this starter build. Connect an authenticated MT5 bridge and explicitly enable live mode.")
    return {"accepted": True, "mode": "DEMO", "order": req.model_dump()}
