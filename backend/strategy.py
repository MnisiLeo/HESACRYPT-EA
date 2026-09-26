from __future__ import annotations
from dataclasses import dataclass, asdict
import math
from typing import List, Dict, Any

@dataclass
class Score:
    m15_structure: int = 0
    crt_sweep: int = 0
    crt_reclaim: int = 0
    ict_liquidity: int = 0
    supply_demand: int = 0
    premium_discount: int = 0
    mss: int = 0
    ob_fvg: int = 0
    stochastic: int = 0
    engulfing: int = 0
    displacement: int = 0

    @property
    def total(self) -> int:
        return sum(asdict(self).values())

    def reasons(self) -> Dict[str, int]:
        return asdict(self)

def _body(c): return abs(c["close"] - c["open"])
def _range(c): return max(c["high"] - c["low"], 1e-12)
def _bull(c): return c["close"] > c["open"]
def _bear(c): return c["close"] < c["open"]

def stochastic(rows: List[dict], period=14):
    if len(rows) < period + 1:
        return None, None
    w = rows[-period:]
    hi = max(x["high"] for x in w)
    lo = min(x["low"] for x in w)
    k = 50.0 if hi == lo else 100.0 * (rows[-1]["close"] - lo) / (hi - lo)
    prev = rows[-2]
    w2 = rows[-period-1:-1]
    hi2 = max(x["high"] for x in w2)
    lo2 = min(x["low"] for x in w2)
    kp = 50.0 if hi2 == lo2 else 100.0 * (prev["close"] - lo2) / (hi2 - lo2)
    return k, kp

def engulfing(rows):
    if len(rows) < 2: return None
    a, b = rows[-2], rows[-1]
    if _bear(a) and _bull(b):
        return b["open"] <= a["close"] and b["close"] >= a["open"]
    if _bull(a) and _bear(b):
        return b["open"] >= a["close"] and b["close"] <= a["open"]
    return False

def analyze(m1: List[dict], m5: List[dict], m15: List[dict], direction_hint=None) -> Dict[str, Any]:
    """
    Deterministic rule engine. Inputs are closed OHLC candles, newest last.
    CRT is represented by the most recently closed M15 candle's high/low.
    """
    s = Score()
    if min(len(m1), len(m5), len(m15)) < 25:
        return {"score": 0, "max_score": 22, "eligible": False,
                "direction": None, "mandatory": False, "reasons": s.reasons(),
                "message": "Need at least 25 candles per timeframe."}

    # M15 structure: simple swing comparison
    p15 = m15[-6:-1]
    hh = m15[-1]["high"] > max(x["high"] for x in p15)
    ll = m15[-1]["low"] < min(x["low"] for x in p15)
    bull_bias = m15[-1]["close"] > m15[-6]["close"]
    bear_bias = m15[-1]["close"] < m15[-6]["close"]
    direction = "BUY" if bull_bias and not bear_bias else "SELL" if bear_bias and not bull_bias else None
    if direction == "BUY" or hh: s.m15_structure = 2
    elif direction == "SELL" or ll: s.m15_structure = 2

    # CRT: previous M15 candle is the range; newest closed M15 candle must reclaim it.
    crt = m15[-2]
    last15 = m15[-1]
    sweep_down = last15["low"] < crt["low"]
    sweep_up = last15["high"] > crt["high"]
    reclaim_down = sweep_down and last15["close"] > crt["low"] and last15["close"] <= crt["high"]
    reclaim_up = sweep_up and last15["close"] < crt["high"] and last15["close"] >= crt["low"]

    if direction == "BUY" and sweep_down: s.crt_sweep = 3
    elif direction == "SELL" and sweep_up: s.crt_sweep = 3
    if direction == "BUY" and reclaim_down: s.crt_reclaim = 2
    elif direction == "SELL" and reclaim_up: s.crt_reclaim = 2

    # M5 liquidity: newest closed candle sweeps a recent 5-candle extreme.
    prior5 = m5[-7:-1]
    sweep5_down = m5[-1]["low"] < min(x["low"] for x in prior5)
    sweep5_up = m5[-1]["high"] > max(x["high"] for x in prior5)
    if (direction == "BUY" and sweep5_down) or (direction == "SELL" and sweep5_up):
        s.ict_liquidity = 2

    # Support/demand and supply/resistance proxy using recent swing zones.
    recent = m5[-20:-1]
    support = min(x["low"] for x in recent)
    resistance = max(x["high"] for x in recent)
    price = m1[-1]["close"]
    near_support = abs(price-support) <= max((resistance-support)*0.12, price*0.0005)
    near_resistance = abs(resistance-price) <= max((resistance-support)*0.12, price*0.0005)
    if direction == "BUY" and near_support: s.supply_demand = 2
    elif direction == "SELL" and near_resistance: s.supply_demand = 2

    # Premium/discount relative to recent M15 range.
    hi = max(x["high"] for x in m15[-20:])
    lo = min(x["low"] for x in m15[-20:])
    eq = (hi+lo)/2
    if direction == "BUY" and price < eq: s.premium_discount = 1
    elif direction == "SELL" and price > eq: s.premium_discount = 1

    # MSS proxy on M1: close breaks last 3-candle swing.
    prior1 = m1[-5:-1]
    if direction == "BUY" and m1[-1]["close"] > max(x["high"] for x in prior1):
        s.mss = 3
    elif direction == "SELL" and m1[-1]["close"] < min(x["low"] for x in prior1):
        s.mss = 3

    # OB/FVG proxy: displacement candle leaves a gap with the previous candle.
    a,b,c = m1[-3],m1[-2],m1[-1]
    bull_gap = c["low"] > a["high"] and _bull(c)
    bear_gap = c["high"] < a["low"] and _bear(c)
    if (direction == "BUY" and bull_gap) or (direction == "SELL" and bear_gap):
        s.ob_fvg = 2

    # Stochastic timing
    k, kp = stochastic(m1)
    if k is not None:
        if direction == "BUY" and kp <= 20 and k > kp: s.stochastic = 1
        elif direction == "SELL" and kp >= 80 and k < kp: s.stochastic = 1

    eng = engulfing(m1)
    if (direction == "BUY" and eng is True and _bull(m1[-1])) or \
       (direction == "SELL" and eng is True and _bear(m1[-1])):
        s.engulfing = 3

    avg_body = sum(_body(x) for x in m1[-11:-1]) / 10
    if avg_body > 0 and _body(m1[-1]) >= 1.25 * avg_body:
        if (direction == "BUY" and _bull(m1[-1])) or (direction == "SELL" and _bear(m1[-1])):
            s.displacement = 1

    mandatory = (
        s.crt_sweep == 3 and
        s.crt_reclaim == 2 and
        s.mss == 3 and
        s.engulfing == 3
    )
    eligible = s.total >= 17 and mandatory and direction is not None

    return {
        "score": s.total, "max_score": 22, "eligible": eligible,
        "direction": direction, "mandatory": mandatory,
        "reasons": s.reasons(), "stochastic": {"k": k, "previous_k": kp},
        "message": "TRADE ELIGIBLE" if eligible else "NO TRADE"
    }
