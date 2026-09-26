# MT5 execution bridge

This bridge is the component that must run on an always-on Windows/VPS machine.

MetaTrader's official Python integration connects to the **desktop MT5 terminal**, not the Android app. It can retrieve ticks/bars and send trading requests through the terminal.

## Setup

1. Install desktop MT5 on the host.
2. Log in to the broker account.
3. Install Python.
4. `pip install -r requirements.txt`
5. Set environment variables:
   - `MT5_LOGIN`
   - `MT5_PASSWORD`
   - `MT5_SERVER`
6. Run `python bridge.py`

Never commit credentials.

## Why this exists

The Android app is the control plane. The bridge is the execution plane. If the bridge/terminal is offline, the phone can still display its own UI but cannot place MT5 orders.

For Exness, use the exact MT5 server name shown in the account/terminal. Do not hard-code a guessed server name.
