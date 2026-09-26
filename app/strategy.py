from dataclasses import dataclass
from statistics import mean

MIN_SCORE = 17

@dataclass
class Result:
    eligible: bool
    score: int
    direction: str|None
    reason: str
    checks: dict
    entry: float|None
    stop: float|None
    target: float|None

def body(c): return abs(c["close"]-c["open"])
def bull(c): return c["close"]>c["open"]
def bear(c): return c["close"]<c["open"]

def stoch(cs,n=14):
    if len(cs)<n: return None
    w=cs[-n:]; hi=max(x["high"] for x in w); lo=min(x["low"] for x in w)
    return 50 if hi==lo else 100*(w[-1]["close"]-lo)/(hi-lo)

def engulf(cs,d):
    if len(cs)<2:return False
    a,b=cs[-2],cs[-1]
    return (d=="BUY" and bear(a) and bull(b) and b["open"]<=a["close"] and b["close"]>=a["open"]) or \
           (d=="SELL" and bull(a) and bear(b) and b["open"]>=a["close"] and b["close"]<=a["open"])

def analyze(m1,m5,m15):
    if min(len(m1),len(m5),len(m15))<40:
        return Result(False,0,None,"Waiting for enough candles.",{},None,None,None).__dict__

    score=0; checks={}
    d="BUY" if m15[-1]["close"]>m15[-8]["close"] else "SELL"
    score+=2; checks["M15 direction"]={"ok":True,"points":2,"value":d}

    crt=m15[-2]; cur=m15[-1]
    sweep=(cur["low"]<crt["low"]) if d=="BUY" else (cur["high"]>crt["high"])
    reclaim=(cur["close"]>crt["low"]) if d=="BUY" else (cur["close"]<crt["high"])
    if sweep:score+=3
    if reclaim:score+=2
    checks["CRT liquidity sweep"]={"ok":sweep,"points":3}
    checks["CRT reclaim"]={"ok":reclaim,"points":2}

    ext=m5[-31:-1]
    lo=min(x["low"] for x in ext); hi=max(x["high"] for x in ext)
    ict=(m5[-1]["low"]<lo) if d=="BUY" else (m5[-1]["high"]>hi)
    if ict:score+=2
    checks["ICT liquidity"]={"ok":ict,"points":2}

    rng=hi-lo or 1e-9
    loc=(m5[-1]["close"]-lo)/rng
    sd=(loc<=.45) if d=="BUY" else (loc>=.55)
    pd=(loc<=.5) if d=="BUY" else (loc>=.5)
    if sd:score+=2
    if pd:score+=1
    checks["Supply / Demand"]={"ok":sd,"points":2}
    checks["Premium / Discount"]={"ok":pd,"points":1}

    p=m1[-7:-1]
    mss=(m1[-1]["close"]>max(x["high"] for x in p)) if d=="BUY" else (m1[-1]["close"]<min(x["low"] for x in p))
    if mss:score+=3
    checks["M1 MSS"]={"ok":mss,"points":3}

    a,b,c=m1[-3],m1[-2],m1[-1]
    fvg=(c["low"]>a["high"]) if d=="BUY" else (c["high"]<a["low"])
    ob=(bull(b) if d=="BUY" else bear(b))
    obfvg=fvg or ob
    if obfvg:score+=2
    checks["OB / FVG"]={"ok":obfvg,"points":2}

    s=stoch(m1); sp=stoch(m1[:-1])
    st=((sp is not None and s is not None and sp<=20 and s>sp) if d=="BUY"
        else (sp is not None and s is not None and sp>=80 and s<sp))
    if st:score+=1
    checks["Stochastic"]={"ok":st,"points":1,"value":round(s,2) if s is not None else None}

    e=engulf(m1,d)
    if e:score+=3
    checks["Engulfing"]={"ok":e,"points":3}

    avg=mean(body(x) for x in m1[-11:-1]) or 1e-9
    disp=body(m1[-1])>=1.25*avg
    if disp:score+=1
    checks["Displacement"]={"ok":disp,"points":1}

    mandatory=sweep and reclaim and mss and e
    eligible=score>=MIN_SCORE and mandatory
    entry=m1[-1]["close"]
    # ATR-like recent range for mechanical protective levels.
    ranges=[x["high"]-x["low"] for x in m1[-15:]]
    vol=max(mean(ranges), 1e-9)
    stop=entry-vol*1.2 if d=="BUY" else entry+vol*1.2
    target=entry+(entry-stop)*2 if d=="BUY" else entry-(stop-entry)*2
    reason="ENTRY GATE PASSED" if eligible else ("Score below 17/22" if score<17 else "Mandatory gate not satisfied")
    return Result(eligible,score,d,reason,checks,entry,stop,target).__dict__
