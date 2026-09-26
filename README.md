# L.Mnisi Full Phone-Only Cloud Trading Product
Samsung A05 -> L.Mnisi frontend -> cloud -> MetaApi -> MT5 broker account.

Includes frontend dashboard, chart, pair/lot controls, DEMO/LIVE gate, score 22/22, BUY/SELL, confirmations, positions/history views, authenticated backend API, cloud MetaApi adapter, automatic analysis/execution loop, position limit/cooldown, emergency close, strategy modules and deployment files.

Stochastic: M1 14-period. BUY confirmation <=5; SELL confirmation >=95; 1 point.

22-point weights: M15 structure 2; CRT sweep 3; CRT reclaim 2; ICT liquidity 2; Supply/Demand 2; Premium/Discount 1; MSS 3; OB/FVG 2; Stochastic 1; Engulfing 3; Displacement 1. Support/Resistance is displayed as an additional confirmation without adding points, preserving 22.

Keep ENABLE_LIVE=false until a connected MT5 demo account is independently tested. Private credentials are not packaged.
