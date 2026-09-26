"""LMnisi M15 -> M5 -> M1 CRT/ICT/SMC strategy.

The strategy is deterministic: no LLM is involved in signal generation.
It uses only CLOSED candles supplied by the broker adapter.
Maximum score is exactly 22 points.
Mandatory gates: CRT sweep + reclaim, M1/M5 MSS, and M1 engulfing.
Stochastic trigger: BUY when the recent stochastic reaches <=5; SELL when it reaches >=95.
"""
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

@dataclass(frozen=True)
class Candle:
    o: float
    h: float
    l: float
    c: float
    t: str = ""
    volume: float = 0.0

def stoch_value(candles: List[Candle], period: int = 14) -> Optional[float]:
    if len(candles) < period:
        return None
    w=candles[-period:]
    lo=min(x.l for x in w); hi=max(x.h for x in w)
    return 50.0 if hi==lo else 100.0*(w[-1].c-lo)/(hi-lo)

def stoch_recent(candles: List[Candle], period: int = 14, lookback: int = 3) -> Tuple[Optional[float], bool, bool]:
    if len(candles) < period+lookback:
        return None, False, False
    vals=[]
    for end in range(len(candles)-lookback, len(candles)):
        vals.append(stoch_value(candles[:end+1], period))
    vals=[v for v in vals if v is not None]
    latest=vals[-1] if vals else None
    return latest, any(v<=5 for v in vals), any(v>=95 for v in vals)

def engulfing(prev: Candle, cur: Candle):
    bull=(prev.c<prev.o and cur.c>cur.o and cur.o<=prev.c and cur.c>=prev.o)
    bear=(prev.c>prev.o and cur.c<cur.o and cur.o>=prev.c and cur.c<=prev.o)
    return bull,bear

def mss(candles: List[Candle], lookback: int = 6):
    if len(candles)<lookback+1: return False,False
    prior=candles[-lookback-1:-1]; cur=candles[-1]
    return cur.c>max(x.h for x in prior), cur.c<min(x.l for x in prior)

def displacement(candles: List[Candle], n: int = 10, mult: float = 1.25):
    if len(candles)<n+1: return False
    body=abs(candles[-1].c-candles[-1].o)
    avg=sum(abs(x.c-x.o) for x in candles[-n-1:-1])/n
    return bool(avg and body>=mult*avg)

def _range(candles):
    hi=max(x.h for x in candles); lo=min(x.l for x in candles)
    return hi,lo,(hi+lo)/2

def analyze(m15: List[Candle], m5: List[Candle], m1: List[Candle]) -> Dict:
    if len(m15)<12 or len(m5)<20 or len(m1)<30:
        return {"qualified":False,"score":0,"max_score":22,"side":"WAIT","raw_side":"WAIT","reason":"Not enough closed candles","checks":{}}

    # M15 directional structure: compare recent closed structure with older structure.
    bull=m15[-1].c>m15[-8].c and m15[-1].c>m15[-2].c
    bear=m15[-1].c<m15[-8].c and m15[-1].c<m15[-2].c
    raw_side="BUY" if bull else "SELL" if bear else "WAIT"

    # CRT = latest CLOSED M15 candle. The latest CLOSED M5 candle must sweep its
    # liquidity and close back inside the CRT range. It does not need to close
    # beyond the liquidity level; only the wick must take it.
    crt=m15[-1]
    sweep_candle=m5[-1]
    sweep=False; reclaim=False
    if bull:
        sweep=sweep_candle.l<crt.l
        reclaim=sweep and sweep_candle.c>=crt.l and sweep_candle.c<=crt.h
    elif bear:
        sweep=sweep_candle.h>crt.h
        reclaim=sweep and sweep_candle.c<=crt.h and sweep_candle.c>=crt.l

    # External liquidity: latest M5 candle takes a recent M5 extreme and closes back inside.
    ext=m5[-7:-1]
    if bull:
        ext_level=min(x.l for x in ext); liq=sweep_candle.l<ext_level and sweep_candle.c>ext_level
    elif bear:
        ext_level=max(x.h for x in ext); liq=sweep_candle.h>ext_level and sweep_candle.c<ext_level
    else: liq=False

    hi,lo,mid=_range(m5[-12:])
    # Supply/demand + support/resistance location proxy: directional candle at an edge.
    pos=(m5[-1].c-lo)/(hi-lo) if hi>lo else 0.5
    demand=(pos<=0.40 and m5[-1].c>=m5[-1].o)
    supply=(pos>=0.60 and m5[-1].c<=m5[-1].o)
    sd_ok=demand if bull else supply if bear else False
    pd_ok=m5[-1].c<=mid if bull else m5[-1].c>=mid if bear else False

    b1,s1=mss(m1); b5,s5=mss(m5)
    mss_ok=(b1 or b5) if bull else (s1 or s5) if bear else False
    eg_bull,eg_bear=engulfing(m1[-2],m1[-1]); eng_ok=eg_bull if bull else eg_bear if bear else False

    st,st_buy,st_sell=stoch_recent(m1)
    st_ok=st_buy if bull else st_sell if bear else False
    disp=displacement(m1)

    a,b,c=m1[-3],m1[-2],m1[-1]
    fvg=(c.l>a.h) if bull else (c.h<a.l) if bear else False
    ob=((b.c>b.o) if bull else (b.c<b.o) if bear else False)
    obfvg=ob or fvg

    checks={
      "M15 directional structure": bull or bear,
      "CRT liquidity sweep": sweep,
      "CRT close/reclaim": reclaim,
      "ICT liquidity": liq,
      "Supply/Demand": sd_ok,
      "Premium/Discount": pd_ok,
      "M1/M5 MSS": mss_ok,
      "Order Block/FVG": obfvg,
      "Stochastic": st_ok,
      "Engulfing": eng_ok,
      "Strong displacement": disp,
    }
    weights={"M15 directional structure":2,"CRT liquidity sweep":3,"CRT close/reclaim":2,"ICT liquidity":2,
              "Supply/Demand":2,"Premium/Discount":1,"M1/M5 MSS":3,"Order Block/FVG":2,"Stochastic":1,
              "Engulfing":3,"Strong displacement":1}
    score=sum(weights[k] for k,v in checks.items() if v)
    mandatory=sweep and reclaim and mss_ok and eng_ok
    qualified=raw_side in ("BUY","SELL") and score>=17 and mandatory
    return {
      "qualified":qualified,"score":score,"max_score":22,
      "side":raw_side if qualified else "WAIT","raw_side":raw_side,
      "stochastic":st,"stoch_buy_reached":st_buy,"stoch_sell_reached":st_sell,
      "mandatory":mandatory,"checks":checks,
      "entry":m1[-1].c if qualified else None,
      "crt":{"high":crt.h,"low":crt.l},
      "m5_sweep":{"high":sweep_candle.h,"low":sweep_candle.l,"close":sweep_candle.c},
      "reason":"Qualified 17/22 + mandatory gates" if qualified else "Conditions not qualified"
    }
