import pandas as pd
from strategy.strategy import analyze
def candles(n=40):
    rows=[]
    for i in range(n):
        p=100+i*0.05
        rows.append({"open":p,"high":p+0.2,"low":p-0.2,"close":p+0.05})
    return pd.DataFrame(rows)
def test_strategy_runs():
    r=analyze(candles(),candles(),candles()); assert 0<=r.score<=22
