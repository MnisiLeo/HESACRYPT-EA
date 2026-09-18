# MnisiLeo — Forex Sniper EA (Android + Cloud Bridge)

This repository is a real Android application codebase plus a modular cloud execution bridge. It is designed around the supplied Forex Sniper specification: M15 → M5 → M1 hierarchy, weighted confluence, 3% maximum per-trade risk, 2→3→3 sequencing, dynamic SL/TP, safety locks, backtesting using the same strategy engine, and modular broker execution.

## Important live-trading limitation

Exness currently documents its supported trading platforms and API terms, but a public, stable retail order-execution REST/WebSocket API specification suitable for embedding arbitrary third-party Android execution was not found in the official material checked while creating this package. Exness documents MT5/WebTerminal/mobile trading and publishes API terms, but this is not the same as a documented public trading API for this app. Therefore this project **does not fake direct Exness execution**. The `BrokerExecution` interface and `bridge/` service are the real integration seam: connect them to an authorized Exness API/bridge when you have the required API access. No credentials are included.

The app can therefore be built and run immediately for strategy analysis/backtesting with real historical OHLC data imported through the data adapter, while live execution remains locked until a configured broker execution adapter is available.

## Build

Requirements: Android Studio Hedgehog+ / JDK 17 / Android SDK 35.

Open `android/` in Android Studio and build the `app` module.

## Safety

- No martingale.
- No averaging down.
- Risk engine has veto authority.
- New entries stop on invalid data, disconnected broker, abnormal spread, daily loss, drawdown, consecutive-loss limit, margin danger, or sequence exposure.
- CLOSE ALL requires confirmation.
- Live mode is explicitly separated from backtest mode.

## Data

The backtester accepts M1 OHLCV bars and derives M5/M15 from the same M1 stream, preserving timeframe synchronization. Trading costs (spread, commission and slippage) are configurable.

## Live bridge

`bridge/` is a small FastAPI service contract. It intentionally does not contain fake broker endpoints or credentials. Configure a compliant execution provider that can supply prices/account/positions and place/modify/close orders. The Android app uses an idempotency key for order requests so network retries cannot intentionally duplicate an order.
