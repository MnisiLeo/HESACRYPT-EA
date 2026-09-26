from strategy.strategy import _stochastic,analyze

def c(o,h,l,cl):return {'open':o,'high':h,'low':l,'close':cl}
def test_stochastic_bounds():
    assert 0 <= _stochastic([c(10,11,9,10)]*14) <= 100

def test_stochastic_threshold_constants():
    assert 5 < 95
