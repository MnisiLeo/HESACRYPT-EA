# L.Mnisi Final Phone-Only Cloud Trading Package

Architecture:
Samsung A05 → L.Mnisi web app → cloud service → MetaApi → MT5 broker account.

No desktop MT5 bridge is included.

## Strategy gate
22 points total, minimum 17/22.
Mandatory: CRT liquidity sweep, CRT reclaim, M1/M5 MSS, engulfing.

## Stochastic
M1, 14-period:
- BUY: oscillator reaches 5 or below.
- SELL: oscillator reaches 95 or above.
Stochastic contributes 1 point.

## Important
The package contains software and deployment configuration. Private broker/MetaApi credentials are intentionally not included.
Keep ENABLE_LIVE=false until the cloud connection and demo-account behavior have been tested.
A persistent cloud host is required for unattended operation; a sleeping/free service is not appropriate for 24/7 execution.
