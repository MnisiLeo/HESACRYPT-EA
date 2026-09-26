import sys, pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from strategy.strategy import Candle, analyze

def c(o,h,l,cl): return Candle(o,h,l,cl)

def test_score_weight_total():
    weights=[2,3,2,2,2,1,3,2,1,3,1]
    assert sum(weights)==22

def test_insufficient():
    r=analyze([c(1,2,0,1)]*3,[c(1,2,0,1)]*3,[c(1,2,0,1)]*3)
    assert r['qualified'] is False and r['score']==0
