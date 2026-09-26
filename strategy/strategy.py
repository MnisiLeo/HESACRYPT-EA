from dataclasses import dataclass
from typing import Dict, List, Optional
import statistics

WEIGHTS = {
    'M15 directional structure': 2, 'CRT liquidity sweep': 3, 'CRT close/reclaim': 2,
    'ICT liquidity': 2, 'Supply/Demand': 2, 'Premium/Discount': 1,
    'M1/M5 MSS': 3, 'Order Block/FVG': 2, 'Stochastic': 1,
    'Engulfing': 3, 'Strong displacement': 1,
}

@dataclass
class Analysis:
    symbol: str; side: str; score: int; eligible: bool; checks: Dict[str,bool]
    stochastic: float; entry: Optional[float]; stop_loss: Optional[float]
    take_profit: Optional[float]; reason: str; sr_level: Optional[float]=None

def _stochastic(candles, period=14):
    if len(candles) < period: return None
    w=candles[-period:]; hi=max(float(x['high']) for x in w); lo=min(float(x['low']) for x in w); close=float(w[-1]['close'])
    return 50.0 if hi==lo else 100*(close-lo)/(hi-lo)

def _engulfing(c,bull):
    if len(c)<2:return False
    a,b=c[-2],c[-1]; ao,ac,bo,bc=map(float,(a['open'],a['close'],b['open'],b['close']))
    return (ac<ao and bc>bo and bo<=ac and bc>=ao) if bull else (ac>ao and bc<bo and bo>=ac and bc<=ao)

def _mss(c,bull,lb=6):
    if len(c)<lb+1:return False
    p=c[-lb-1:-1]; last=float(c[-1]['close'])
    return last>max(float(x['high']) for x in p) if bull else last<min(float(x['low']) for x in p)

def _crt(m,bull):
    if len(m)<3:return False,False
    r=m[-2]; x=m[-1]; hi,lo=float(r['high']),float(r['low'])
    swept=float(x['low'])<lo if bull else float(x['high'])>hi
    reclaim=(lo<float(x['close'])<hi)
    return swept,reclaim

def _liq(c,bull):
    if len(c)<8:return False
    p=c[-7:-1]; x=c[-1]
    return float(x['low'])<min(float(z['low']) for z in p) if bull else float(x['high'])>max(float(z['high']) for z in p)

def _sd_sr_pd(c,bull):
    if len(c)<20:return False,False,False,None
    w=c[-20:]; hi=max(float(x['high']) for x in w); lo=min(float(x['low']) for x in w); mid=(hi+lo)/2; close=float(w[-1]['close'])
    # Location proxy: demand/support below midpoint for buys; supply/resistance above for sells.
    loc=close<=mid if bull else close>=mid
    # Explicit S/R proximity to recent swing extreme.
    level=lo if bull else hi
    span=max(hi-lo,1e-12); sr=abs(close-level)<=span*0.25
    return loc, sr, loc, level

def _ob_fvg(c,bull):
    if len(c)<4:return False
    a,b,x=c[-3],c[-2],c[-1]
    fvg=float(x['low'])>float(a['high']) if bull else float(x['high'])<float(a['low'])
    ob=float(b['close'])>float(b['open']) if bull else float(b['close'])<float(b['open'])
    return fvg or ob

def _disp(c):
    if len(c)<11:return False
    avg=statistics.mean(abs(float(x['close'])-float(x['open'])) for x in c[-11:-1]); body=abs(float(c[-1]['close'])-float(c[-1]['open']))
    return bool(avg and body>=1.25*avg)

def analyze(symbol,m15,m5,m1):
    if min(len(m15),len(m5),len(m1))<20:
        return Analysis(symbol,'WAIT',0,False,{},50,None,None,None,'Not enough data')
    bull_bias=float(m15[-1]['close'])>float(m15[-7]['close']); bear_bias=float(m15[-1]['close'])<float(m15[-7]['close'])
    candidates=[]
    for bull in (True,False):
        side='BUY' if bull else 'SELL'; bias=bull_bias if bull else bear_bias; sweep,reclaim=_crt(m15,bull); liq=_liq(m5,bull)
        sd,sr,pd,level=_sd_sr_pd(m5,bull); mss=_mss(m1,bull); ob=_ob_fvg(m1,bull); st=_stochastic(m1)
        st_ok=(st is not None and st<=5) if bull else (st is not None and st>=95)
        eng=_engulfing(m1,bull); disp=_disp(m1)
        checks={'M15 directional structure':bias,'CRT liquidity sweep':sweep,'CRT close/reclaim':reclaim,'ICT liquidity':liq,
                'Supply/Demand':sd,'Support/Resistance':sr,'Premium/Discount':pd,'M1/M5 MSS':mss,'Order Block/FVG':ob,
                'Stochastic':st_ok,'Engulfing':eng,'Strong displacement':disp}
        # S/R is descriptive confirmation only and does not add a new point to preserve the 22-point system.
        score=sum(WEIGHTS[k] for k,v in checks.items() if k in WEIGHTS and v)
        mandatory=sweep and reclaim and mss and eng
        eligible=score>=17 and mandatory
        entry=sl=tp=None
        if eligible:
            entry=float(m1[-1]['close']); rng=max(float(x['high'])-float(x['low']) for x in m1[-10:]); risk=max(rng,entry*0.0005)
            sl=entry-risk if bull else entry+risk; tp=entry+2*risk if bull else entry-2*risk
        candidates.append(Analysis(symbol,side,score,eligible,checks,float(st or 50),entry,sl,tp,f'{side} {score}/22 | Stoch {st:.2f} | BUY<=5 SELL>=95',level))
    eligible=[x for x in candidates if x.eligible]
    if eligible:return max(eligible,key=lambda x:x.score)
    return max(candidates,key=lambda x:x.score)
