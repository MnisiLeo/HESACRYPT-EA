from app.strategy import analyze
def c(o,h,l,cl): return {'open':o,'high':h,'low':l,'close':cl}
m1=[c(1,1.1,.9,1.02) for _ in range(50)]
m5=[c(1,1.1,.9,1.02) for _ in range(50)]
m15=[c(1,1.1,.9,1.02) for _ in range(50)]
r=analyze(m1,m5,m15)
assert 'score' in r
print('strategy smoke test passed', r['score'])
