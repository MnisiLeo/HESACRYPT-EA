# L.Mnisi Cloud Trading System

Phone-first cloud trading control panel for MT5 accounts through MetaApi. The Samsung phone is the control panel; the trading engine runs on the cloud service.

## Current implementation
- Real MetaApi REST connection for account, positions, candles and trade execution.
- Closed-candle M15 -> M5 -> M1 analysis.
- 22-point CRT/ICT/SMC/Supply-Demand/Support-Resistance/Stochastic/Engulfing score.
- BUY stochastic trigger <=5 and SELL trigger >=95, including a recent 3-candle reach.
- Mandatory CRT sweep + reclaim, M1/M5 MSS and M1 engulfing.
- Market order sends protective SL and configurable RR take-profit in the same MetaApi request.
- Position limit and trade cooldown.
- Emergency close endpoint.
- LIVE mode has a server-side ALLOW_LIVE_TRADING safety gate.
- No MetaApi credentials are stored in the web UI.

## Important
The strategy is rule-based and deterministic. It is not a guarantee of profit. DEMO testing should be completed before enabling live execution.

## Render
Deploy the repository root containing this Dockerfile. Do not set a Root Directory. Add the environment variables from `.env.example` in Render.

## MetaApi
MetaApi is the cloud bridge between this service and an MT4/MT5 account. A MetaApi token and account ID are required before real broker data/execution can occur.
