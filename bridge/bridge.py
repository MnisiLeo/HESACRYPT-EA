import os
import MetaTrader5 as mt5
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="MT5 Bridge")

LOGIN = int(os.environ.get("MT5_LOGIN", "0"))
PASSWORD = os.environ.get("MT5_PASSWORD", "")
SERVER = os.environ.get("MT5_SERVER", "")

def connect():
    ok = mt5.initialize(login=LOGIN, password=PASSWORD, server=SERVER)
    if not ok:
        raise HTTPException(503, f"MT5 initialize failed: {mt5.last_error()}")
    return True

class Order(BaseModel):
    symbol: str
    direction: str
    volume: float
    sl: float | None = None
    tp: float | None = None
    magic: int = 260926

@app.get("/status")
def status():
    if not connect():
        return {"connected": False}
    info = mt5.account_info()
    return {
        "connected": info is not None,
        "login": getattr(info, "login", None),
        "server": getattr(info, "server", None),
        "balance": getattr(info, "balance", None),
        "equity": getattr(info, "equity", None),
    }

@app.get("/bars/{symbol}")
def bars(symbol: str, timeframe: str = "M1", count: int = 300):
    if not connect():
        raise HTTPException(503, "MT5 unavailable")
    tf = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15}.get(timeframe)
    if tf is None:
        raise HTTPException(400, "Unsupported timeframe")
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None:
        raise HTTPException(404, f"No rates for {symbol}: {mt5.last_error()}")
    return [
        {"time": int(x["time"]), "open": float(x["open"]), "high": float(x["high"]),
         "low": float(x["low"]), "close": float(x["close"]), "volume": float(x["tick_volume"])}
        for x in rates
    ]

@app.post("/order")
def place(order: Order):
    if not connect():
        raise HTTPException(503, "MT5 unavailable")
    if not mt5.symbol_select(order.symbol, True):
        raise HTTPException(400, f"Cannot select {order.symbol}")
    tick = mt5.symbol_info_tick(order.symbol)
    if tick is None:
        raise HTTPException(400, "No tick")
    is_buy = order.direction.upper() == "BUY"
    price = tick.ask if is_buy else tick.bid
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": order.symbol,
        "volume": order.volume,
        "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": order.sl or 0.0,
        "tp": order.tp or 0.0,
        "deviation": 20,
        "magic": order.magic,
        "comment": "CRT17",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result is None:
        raise HTTPException(502, f"order_send returned None: {mt5.last_error()}")
    return {"retcode": result.retcode, "comment": result.comment,
            "order": result.order, "deal": result.deal}
