"""L.Mnisi cloud trading engine.

M15 -> M5 -> M1 CRT / ICT / SMC strategy.
MetaApi is used as the cloud MT5 connection.
"""

import os
import time
import threading
import logging
import uuid
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import requests

from strategy import Candle, analyze

logger = logging.getLogger("lmnisi")


class MetaApiREST:
    def __init__(self):
        self.token = os.getenv("METAAPI_TOKEN", "").strip()
        self.account_id = os.getenv("METAAPI_ACCOUNT_ID", "").strip()

        self.client_base = os.getenv(
            "METAAPI_CLIENT_BASE",
            "https://mt-client-api-v1.new-york.agiliumtrade.ai"
        ).rstrip("/")

        self.market_base = os.getenv(
            "METAAPI_MARKET_BASE",
            "https://mt-market-data-client-api-v1.new-york.agiliumtrade.ai"
        ).rstrip("/")

        self.timeout = float(os.getenv("METAAPI_TIMEOUT", "20"))
        self.session = requests.Session()
        self.connected = False
        self.last_error = ""

    @property
    def configured(self):
        return bool(self.token and self.account_id)

    def _headers(self):
        return {
            "auth-token": self.token,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def _get(self, base, path, params=None):
        response = self.session.get(
            base + path,
            headers=self._headers(),
            params=params,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def _post(self, base, path, payload):
        response = self.session.post(
            base + path,
            headers=self._headers(),
            json=payload,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def account(self):
        if not self.configured:
            return None

        return self._get(
            self.client_base,
            f"/users/current/accounts/{self.account_id}/account-information",
            {"refreshTerminalState": "true"}
        )

    def positions(self):
        if not self.configured:
            return []

        return self._get(
            self.client_base,
            f"/users/current/accounts/{self.account_id}/positions",
            {"refreshTerminalState": "true"}
        )

    def candles(self, symbol, timeframe, limit=100):
        if not self.configured:
            return []

        data = self._get(
            self.market_base,
            f"/users/current/accounts/{self.account_id}/"
            f"historical-market-data/symbols/{symbol}/"
            f"timeframes/{timeframe}/candles",
            {"limit": min(limit, 1000)}
        )

        if not isinstance(data, list):
            return []

        data = sorted(
            data,
            key=lambda x: x.get("time", x.get("brokerTime", ""))
        )

        return data[-limit:]

    def trade(
        self,
        action,
        symbol,
        volume,
        stop_loss=None,
        take_profit=None,
        comment="LMnisi",
        client_id=None
    ):
        payload = {
            "actionType": action,
            "symbol": symbol,
            "volume": float(volume),
            "magic": 260926,
            "comment": comment[:16],
            "clientId": (
                client_id or
                ("LM" + uuid.uuid4().hex[:10])
            )[:20]
        }

        if stop_loss is not None:
            payload["stopLoss"] = float(stop_loss)

        if take_profit is not None:
            payload["takeProfit"] = float(take_profit)

        return self._post(
            self.client_base,
            f"/users/current/accounts/{self.account_id}/trade",
            payload
        )

    def close_position(self, position_id):
        return self._post(
            self.client_base,
            f"/users/current/accounts/{self.account_id}/trade",
            {
                "actionType": "POSITION_CLOSE_ID",
                "positionId": str(position_id)
            }
        )


class TradingEngine:
    def __init__(self, state):
        self.state = state
        self.api = MetaApiREST()

        self.stop_event = threading.Event()
        self.thread = None
        self.lock = threading.Lock()

        self.last_trade_at = 0.0

        self.poll_seconds = max(
            10,
            int(os.getenv("ENGINE_POLL_SECONDS", "20"))
        )

        self.cooldown_seconds = max(
            60,
            int(os.getenv("TRADE_COOLDOWN_SECONDS", "180"))
        )

        self.rr = float(
            os.getenv("TAKE_PROFIT_RR", "2.0")
        )

        self.sl_buffer = float(
            os.getenv("SL_BUFFER_ATR", "0.25")
        )

        self.allow_live = (
            os.getenv("ALLOW_LIVE_TRADING", "false").lower()
            == "true"
        )

        self.max_positions = int(
            os.getenv("MAX_POSITIONS", "1")
        )

    def start(self):
        self.stop_event.clear()

        if self.thread and self.thread.is_alive():
            return

        self.thread = threading.Thread(
            target=self.run,
            daemon=True
        )

        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.state["running"] = False

    def _atr(self, candles, n=14):
        if len(candles) < n + 1:
            return 0.0

        trs = []

        for i in range(-n, 0):
            cur = candles[i]
            prev = candles[i - 1]

            trs.append(
                max(
                    cur.h - cur.l,
                    abs(cur.h - prev.c),
                    abs(cur.l - prev.c)
                )
            )

        return sum(trs) / len(trs)

    def _update_connection(self):
        if not self.api.configured:
            self.state.update({
                "connected": False,
                "status": "WAITING_FOR_METAAPI"
            })
            return None

        try:
            account = self.api.account()

            self.api.connected = True

            self.state["connected"] = True

            if account:
                self.state["balance"] = float(
                    account.get("balance", 0)
                )

                self.state["equity"] = float(
                    account.get("equity", 0)
                )

                self.state["account_type"] = account.get(
                    "type",
                    ""
                )

            return account

        except Exception as exc:
            self.api.connected = False

            self.state["connected"] = False
            self.state["status"] = "BROKER_ERROR"
            self.state["last_error"] = str(exc)[:300]

            return None

    def _analyse(self):
        symbol = self.state["pair"]

        raw = {}

        for timeframe in ("15m", "5m", "1m"):
            raw[timeframe] = self.api.candles(
                symbol,
                timeframe,
                100
            )

        def convert(items):
            return [
                Candle(
                    float(x["open"]),
                    float(x["high"]),
                    float(x["low"]),
                    float(x["close"]),
                    str(x.get("time", "")),
                    float(
                        x.get(
                            "volume",
                            x.get("tickVolume", 0)
                        )
                    )
                )
                for x in items
            ]

        m15 = convert(raw["15m"])
        m5 = convert(raw["5m"])
        m1 = convert(raw["1m"])

        result = analyze(m15, m5, m1)

        result["market_time"] = (
            raw["1m"][-1].get("time")
            if raw["1m"]
            else None
        )

        result["atr"] = self._atr(m1)

        return result, m1

    def _can_trade(self, signal):
        if not signal.get("qualified"):
            return False, "signal_not_qualified"

        if time.time() - self.last_trade_at < self.cooldown_seconds:
            return False, "cooldown"

        try:
            positions = self.api.positions()
        except Exception:
            return False, "positions_unavailable"

        if len(positions) >= self.max_positions:
            return False, "max_positions"

        mode = self.state.get("mode", "DEMO").upper()

        account_type = str(
            self.state.get("account_type", "")
        ).upper()

        if mode == "LIVE":

            if not self.allow_live:
                return False, "LIVE_TRADING_DISABLED"

            if "REAL" not in account_type:
                return False, "LIVE_REQUIRES_REAL_ACCOUNT"

        elif mode == "DEMO":

            if (
                account_type
                and "DEMO" not in account_type
                and "CONTEST" not in account_type
            ):
                return False, "DEMO_MODE_REQUIRES_DEMO_ACCOUNT"

        else:
            return False, "invalid_mode"

        return True, "ok"

    def _execute(self, signal, m1):
        allowed, reason = self._can_trade(signal)

        if not allowed:
            self.state["execution_status"] = reason
            return

        entry = float(signal["entry"])
        atr = float(signal.get("atr") or 0)

        if atr <= 0:
            return

        recent = m1[-6:]

        if signal["side"] == "BUY":

            sl = (
                min(x.l for x in recent)
                - atr * self.sl_buffer
            )

            risk = entry - sl
            tp = entry + risk * self.rr

            action = "ORDER_TYPE_BUY"

        else:

            sl = (
                max(x.h for x in recent)
                + atr * self.sl_buffer
            )

            risk = sl - entry
            tp = entry - risk * self.rr

            action = "ORDER_TYPE_SELL"

        if risk <= 0:
            return

        result = self.api.trade(
            action,
            self.state["pair"],
            self.state["lot"],
            sl,
            tp
        )

        self.last_trade_at = time.time()

        self.state["last_order"] = result
        self.state["execution_status"] = "ORDER_SENT"

    def run(self):
        self.state["status"] = "STARTING"

        while not self.stop_event.is_set():

            try:

                account = self._update_connection()

                if account and self.state.get("running"):

                    signal, m1 = self._analyse()

                    self.state["last_signal"] = signal

                    for key in (
                        "score",
                        "max_score",
                        "raw_side",
                        "stochastic",
                        "mandatory",
                        "checks",
                        "qualified",
                        "entry",
                        "reason",
                        "market_time",
                        "atr",
                        "stoch_buy_reached",
                        "stoch_sell_reached"
                    ):
                        if key in signal:
                            self.state[key] = signal[key]

                    self.state["signal"] = signal.get(
                        "side",
                        "WAIT"
                    )

                    self.state["status"] = "RUNNING"

                    if signal.get("qualified"):
                        self._execute(signal, m1)

                elif self.state.get("running"):

                    self.state["status"] = (
                        "WAITING_FOR_CONNECTION"
                    )

                self.state["last_update"] = (
                    datetime.now(timezone.utc).isoformat()
                )

            except Exception as exc:

                logger.exception(
                    "engine cycle failed"
                )

                self.state["last_error"] = str(exc)[:500]
                self.state["status"] = "ENGINE_ERROR"

            self.stop_event.wait(
                self.poll_seconds
            )


class Engine:
    """Compatibility layer used by backend/main.py."""

    def __init__(self):

        self.state = {
            "running": False,
            "mode": "DEMO",
            "pair": os.getenv(
                "DEFAULT_SYMBOL",
                "XAUUSD"
            ),
            "lot": float(
                os.getenv(
                    "DEFAULT_LOT",
                    "0.01"
                )
            ),
            "connected": False,
            "balance": None,
            "equity": None,
            "score": 0,
            "max_score": 22,
            "signal": "WAIT",
            "reason": "Waiting for cloud connection.",
            "checks": {},
            "log": []
        }

        self.engine = TradingEngine(
            self.state
        )

        self.api = self.engine.api

    @property
    def running(self):
        return bool(
            self.state.get("running", False)
        )

    @property
    def mode(self):
        return self.state.get(
            "mode",
            "DEMO"
        )

    @mode.setter
    def mode(self, value):
        self.state["mode"] = str(
            value
        ).upper()

    @property
    def symbol(self):
        return self.state.get(
            "pair",
            "XAUUSD"
        )

    @symbol.setter
    def symbol(self, value):
        self.state["pair"] = str(value)

    @property
    def last(self):
        signal = self.state.get(
            "last_signal",
            {}
        )

        checks = signal.get(
            "checks",
            {}
        )

        return SimpleNamespace(
            score=signal.get(
                "score",
                self.state.get("score", 0)
            ),
            side=signal.get(
                "side",
                self.state.get("signal", "WAIT")
            ),
            reason=signal.get(
                "reason",
                self.state.get(
                    "reason",
                    "Waiting"
                )
            ),
            bias=checks.get(
                "M15 directional structure",
                False
            ),
            sweep=checks.get(
                "CRT liquidity sweep",
                False
            ),
            mss=checks.get(
                "M1/M5 MSS",
                False
            ),
            engulfing=checks.get(
                "Engulfing",
                False
            ),
            stoch=checks.get(
                "Stochastic",
                False
            ),
            displacement=checks.get(
                "Strong displacement",
                False
            )
        )

    @property
    def log(self):
        items = []

        status = self.state.get("status")

        if status:
            items.append(
                "STATUS: " + str(status)
            )

        if self.state.get("connected"):
            items.append(
                "MetaApi: CONNECTED"
            )
        else:
            items.append(
                "MetaApi: NOT CONNECTED"
            )

        if self.state.get("last_error"):
            items.append(
                "ERROR: " +
                str(self.state["last_error"])
            )

        if self.state.get("execution_status"):
            items.append(
                "EXECUTION: " +
                str(self.state["execution_status"])
            )

        return items[-30:]

    def start(self):
        self.state["running"] = True
        self.engine.start()

    def stop(self):
        self.engine.stop()
        self.state["running"] = False
