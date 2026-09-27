"""L.Mnisi cloud trading engine.

Cloud flow:
Android -> Render/FastAPI -> MetaApi -> MT5 broker.

The phone never needs a desktop MT5 terminal.
"""

import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
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
            "https://mt-client-api-v1.new-york.agiliumtrade.ai",
        ).rstrip("/")

        self.market_base = os.getenv(
            "METAAPI_MARKET_BASE",
            "https://mt-market-data-client-api-v1.new-york.agiliumtrade.ai",
        ).rstrip("/")

        self.timeout = max(
            5.0,
            float(os.getenv("METAAPI_TIMEOUT", "25")),
        )

        self.session = requests.Session()
        self.connected = False
        self.last_error = ""

    @property
    def configured(self):
        return bool(self.token and self.account_id)

    def ready(self):
        """Return whether the cloud engine currently has a live MetaApi connection.

        This is deliberately a method because backend/main.py calls ready().
        """
        return bool(self.configured and self.connected)

    def _headers(self):
        return {
            "auth-token": self.token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _get(self, base, path, params=None):
        response = self.session.get(
            base + path,
            headers=self._headers(),
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def _post(self, base, path, payload):
        response = self.session.post(
            base + path,
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()

        if not response.content:
            return {"ok": True}

        return response.json()

    def account(self):
        if not self.configured:
            return None

        return self._get(
            self.client_base,
            f"/users/current/accounts/{self.account_id}/account-information",
            {"refreshTerminalState": "true"},
        )

    def positions(self):
        if not self.configured:
            return []

        data = self._get(
            self.client_base,
            f"/users/current/accounts/{self.account_id}/positions",
            {"refreshTerminalState": "false"},
        )

        return data if isinstance(data, list) else []

    def candles(self, symbol, timeframe, limit=100):
        if not self.configured:
            return []

        data = self._get(
            self.market_base,
            f"/users/current/accounts/{self.account_id}/"
            f"historical-market-data/symbols/{symbol}/"
            f"timeframes/{timeframe}/candles",
            {"limit": min(max(30, int(limit)), 1000)},
        )

        if not isinstance(data, list):
            return []

        return sorted(
            data,
            key=lambda item: item.get(
                "time",
                item.get("brokerTime", ""),
            ),
        )[-limit:]

    def trade(
        self,
        action,
        symbol,
        volume,
        stop_loss=None,
        take_profit=None,
    ):
        payload = {
            "actionType": action,
            "symbol": symbol,
            "volume": float(volume),
            "magic": 260926,
            "comment": "LMnisi"[:16],
            "clientId": (
                "LM" + uuid.uuid4().hex[:10]
            )[:20],
        }

        if stop_loss is not None:
            payload["stopLoss"] = float(stop_loss)

        if take_profit is not None:
            payload["takeProfit"] = float(take_profit)

        return self._post(
            self.client_base,
            f"/users/current/accounts/{self.account_id}/trade",
            payload,
        )

    def close_position(self, position_id):
        return self._post(
            self.client_base,
            f"/users/current/accounts/{self.account_id}/trade",
            {
                "actionType": "POSITION_CLOSE_ID",
                "positionId": str(position_id),
            },
        )


class TradingEngine:
    def __init__(self, state):
        self.state = state
        self.api = MetaApiREST()

        self.stop_event = threading.Event()
        self.thread = None
        self.lock = threading.RLock()

        self.last_trade_at = 0.0
        self.last_signal_key = ""

        self.poll_seconds = max(
            10,
            int(os.getenv("ENGINE_POLL_SECONDS", "20")),
        )

        self.cooldown_seconds = max(
            60,
            int(os.getenv("TRADE_COOLDOWN_SECONDS", "180")),
        )

        self.rr = max(
            0.5,
            float(os.getenv("TAKE_PROFIT_RR", "2.0")),
        )

        self.sl_buffer = max(
            0.0,
            float(os.getenv("SL_BUFFER_ATR", "0.25")),
        )

        self.allow_live = (
            os.getenv(
                "ALLOW_LIVE_TRADING",
                "false",
            ).lower()
            == "true"
        )

        self.max_positions = max(
            1,
            int(os.getenv("MAX_POSITIONS", "1")),
        )

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                self.state["running"] = True
                self.state["status"] = "RUNNING"
                return

            self.stop_event.clear()
            self.state["running"] = True
            self.state["status"] = "STARTING"

            self.thread = threading.Thread(
                target=self.run,
                name="LMnisiEngine",
                daemon=True,
            )
            self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.state["running"] = False
        self.state["status"] = "STOPPED"
        self.state["execution_status"] = "STOPPED"

    def set_symbol(self, symbol):
        symbol = str(symbol or "").strip().upper()

        if not symbol or len(symbol) > 32:
            raise ValueError("Invalid trading symbol")

        self.state["pair"] = symbol
        self.state["symbol"] = symbol

    def set_lot(self, lot):
        lot = float(lot)

        if lot <= 0 or lot > 100:
            raise ValueError(
                "Lot size must be greater than 0 and no more than 100"
            )

        self.state["lot"] = lot

    def set_mode(self, mode):
        mode = str(mode or "").strip().lower()

        if mode not in ("demo", "live"):
            raise ValueError("Mode must be demo or live")

        self.state["mode"] = mode.upper()

    def _log(self, message):
        logs = self.state.setdefault("log", [])

        logs.append(
            datetime.now(timezone.utc).strftime(
                "%H:%M:%S UTC"
            )
            + " "
            + str(message)
        )

        del logs[:-50]

    def _atr(self, candles, period=14):
        if len(candles) < period + 1:
            return 0.0

        values = []

        for i in range(-period, 0):
            current = candles[i]
            previous = candles[i - 1]

            values.append(
                max(
                    current.h - current.l,
                    abs(current.h - previous.c),
                    abs(current.l - previous.c),
                )
            )

        return sum(values) / len(values)

    def _convert(self, raw):
        return [
            Candle(
                float(item["open"]),
                float(item["high"]),
                float(item["low"]),
                float(item["close"]),
                str(item.get("time", "")),
                float(
                    item.get(
                        "volume",
                        item.get("tickVolume", 0),
                    )
                ),
            )
            for item in raw
        ]

    def _update_connection(self):
        if not self.api.configured:
            self.api.connected = False
            self.state["connected"] = False
            self.state["status"] = "METAAPI_NOT_CONFIGURED"
            self.state["last_error"] = (
                "METAAPI_TOKEN and METAAPI_ACCOUNT_ID "
                "are not configured in Render."
            )
            return None

        try:
            account = self.api.account()

            if not account:
                raise RuntimeError(
                    "MetaApi returned no account information."
                )

            self.api.connected = True
            self.api.last_error = ""

            self.state["connected"] = True
            self.state["status"] = "CONNECTED"

            self.state["balance"] = account.get(
                "balance"
            )
            self.state["equity"] = account.get(
                "equity"
            )

            self.state["account_type"] = str(
                account.get(
                    "type",
                    account.get(
                        "accountType",
                        "",
                    ),
                )
            )

            self.state["server"] = str(
                account.get("server", "")
            )

            self.state["broker"] = str(
                account.get("broker", "")
            )

            return account

        except Exception as exc:
            self.api.connected = False
            self.api.last_error = str(exc)

            self.state["connected"] = False
            self.state["status"] = "BROKER_ERROR"
            self.state["last_error"] = str(exc)[:500]

            self._log(
                "MetaApi: " + str(exc)
            )

            return None

    def _analyse(self):
        symbol = self.state["pair"]

        raw15 = self.api.candles(
            symbol,
            "15m",
            120,
        )
        raw5 = self.api.candles(
            symbol,
            "5m",
            120,
        )
        raw1 = self.api.candles(
            symbol,
            "1m",
            120,
        )

        m15 = self._convert(raw15)
        m5 = self._convert(raw5)
        m1 = self._convert(raw1)

        result = analyze(
            m15,
            m5,
            m1,
        )

        result["market_time"] = (
            raw1[-1].get("time")
            if raw1
            else None
        )

        result["atr"] = self._atr(m1)

        return result, m1

    def _is_demo_account(self):
        text = " ".join(
            [
                str(
                    self.state.get(
                        "account_type",
                        "",
                    )
                ),
                str(
                    self.state.get(
                        "server",
                        "",
                    )
                ),
                str(
                    self.state.get(
                        "broker",
                        "",
                    )
                ),
            ]
        ).lower()

        return any(
            word in text
            for word in (
                "demo",
                "practice",
                "test",
            )
        )

    def _can_trade(self, signal):
        if not signal.get("qualified"):
            return False, "SIGNAL_NOT_QUALIFIED"

        if (
            time.time() - self.last_trade_at
            < self.cooldown_seconds
        ):
            return False, "TRADE_COOLDOWN"

        try:
            positions = self.api.positions()
        except Exception as exc:
            return False, (
                "POSITIONS_UNAVAILABLE: "
                + str(exc)[:120]
            )

        if len(positions) >= self.max_positions:
            return False, "MAX_POSITIONS_REACHED"

        mode = str(
            self.state.get(
                "mode",
                "DEMO",
            )
        ).upper()

        account_type = str(
            self.state.get(
                "account_type",
                "",
            )
        ).upper()

        if mode == "LIVE":
            if not self.allow_live:
                return False, "LIVE_TRADING_DISABLED"

            if "REAL" not in account_type:
                return False, (
                    "LIVE_REQUIRES_REAL_ACCOUNT"
                )

        elif mode == "DEMO":
            if (
                account_type
                and "DEMO" not in account_type
                and "CONTEST" not in account_type
                and not self._is_demo_account()
            ):
                return False, (
                    "DEMO_REQUIRES_DEMO_ACCOUNT"
                )

        else:
            return False, "INVALID_MODE"

        return True, "READY"

    def _execute(self, signal, m1):
        allowed, reason = self._can_trade(signal)

        self.state["execution_status"] = reason

        if not allowed:
            return

        if len(m1) < 20:
            self.state["execution_status"] = (
                "NOT_ENOUGH_M1_DATA"
            )
            return

        entry = float(
            signal.get("entry")
            or m1[-1].c
        )

        atr = float(
            signal.get("atr")
            or 0
        )

        if atr <= 0:
            self.state["execution_status"] = "INVALID_ATR"
            return

        recent = m1[-6:]

        if signal["side"] == "BUY":
            stop_loss = (
                min(item.l for item in recent)
                - atr * self.sl_buffer
            )
            risk = entry - stop_loss
            take_profit = (
                entry + risk * self.rr
            )
            action = "ORDER_TYPE_BUY"

        elif signal["side"] == "SELL":
            stop_loss = (
                max(item.h for item in recent)
                + atr * self.sl_buffer
            )
            risk = stop_loss - entry
            take_profit = (
                entry - risk * self.rr
            )
            action = "ORDER_TYPE_SELL"

        else:
            return

        if risk <= 0:
            self.state["execution_status"] = "INVALID_RISK"
            return

        signal_key = (
            f"{signal.get('market_time')}:"
            f"{signal['side']}"
        )

        if signal_key == self.last_signal_key:
            self.state["execution_status"] = (
                "SIGNAL_ALREADY_PROCESSED"
            )
            return

        try:
            result = self.api.trade(
                action,
                self.state["pair"],
                self.state["lot"],
                stop_loss,
                take_profit,
            )

            self.last_trade_at = time.time()
            self.last_signal_key = signal_key

            self.state["last_order"] = result
            self.state["execution_status"] = "ORDER_SENT"

            self._log(
                f"{signal['side']} "
                f"{self.state['pair']} "
                f"lot={self.state['lot']} "
                f"score={signal.get('score')}/22"
            )

        except Exception as exc:
            self.state["execution_status"] = "ORDER_ERROR"
            self.state["last_error"] = str(exc)[:500]
            self._log(
                "Order: " + str(exc)
            )

    def run(self):
        self.state["status"] = "STARTING"
        self._log("Engine started")

        while not self.stop_event.is_set():
            try:
                account = self._update_connection()

                if (
                    account
                    and self.state.get("running")
                ):
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
                        "stoch_sell_reached",
                        "crt",
                        "m5_sweep",
                    ):
                        if key in signal:
                            self.state[key] = signal[key]

                    self.state["signal"] = signal.get(
                        "side",
                        "WAIT",
                    )

                    self.state["status"] = "RUNNING"

                    if signal.get("qualified"):
                        self._execute(
                            signal,
                            m1,
                        )

                elif self.state.get("running"):
                    self.state["status"] = (
                        "WAITING_FOR_METAAPI"
                    )

                self.state["last_update"] = (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                )

            except Exception as exc:
                logger.exception(
                    "Engine cycle failed"
                )

                self.state["status"] = "ENGINE_ERROR"
                self.state["last_error"] = str(exc)[:500]
                self._log(
                    "Engine: " + str(exc)
                )

            self.stop_event.wait(
                self.poll_seconds
            )


class Engine:
    """Compatibility facade used by backend.main."""

    def __init__(self):
        default_symbol = os.getenv(
            "DEFAULT_SYMBOL",
            "XAUUSD",
        ).upper()

        default_lot = float(
            os.getenv(
                "DEFAULT_LOT",
                "0.01",
            )
        )

        self.state = {
            "running": False,
            "mode": os.getenv(
                "TRADING_MODE",
                "DEMO",
            ).upper(),
            "pair": default_symbol,
            "symbol": default_symbol,
            "lot": default_lot,
            "connected": False,
            "status": "READY",
            "balance": None,
            "equity": None,
            "account_type": "",
            "server": "",
            "broker": "",
            "score": 0,
            "max_score": 22,
            "signal": "WAIT",
            "raw_side": "WAIT",
            "reason": (
                "Connect MetaApi to begin analysis."
            ),
            "qualified": False,
            "execution_status": "IDLE",
            "checks": {},
            "log": [],
            "last_error": "",
        }

        self.engine = TradingEngine(
            self.state
        )

        self.api = self.engine.api

    @property
    def running(self):
        return bool(
            self.state.get(
                "running",
                False,
            )
        )

    @property
    def mode(self):
        return self.state.get(
            "mode",
            "DEMO",
        )

    @mode.setter
    def mode(self, value):
        self.engine.set_mode(value)

    @property
    def symbol(self):
        return self.state.get(
            "pair",
            "XAUUSD",
        )

    @symbol.setter
    def symbol(self, value):
        self.engine.set_symbol(value)

    @property
    def lot(self):
        return float(
            self.state.get(
                "lot",
                0.01,
            )
        )

    @lot.setter
    def lot(self, value):
        self.engine.set_lot(value)

    @property
    def last(self):
        signal = self.state.get(
            "last_signal",
            {},
        )

        checks = signal.get(
            "checks",
            {},
        )

        return SimpleNamespace(
            score=signal.get(
                "score",
                self.state.get(
                    "score",
                    0,
                ),
            ),
            side=signal.get(
                "side",
                self.state.get(
                    "signal",
                    "WAIT",
                ),
            ),
            reason=signal.get(
                "reason",
                self.state.get(
                    "reason",
                    "Waiting",
                ),
            ),
            bias=checks.get(
                "M15 directional structure",
                False,
            ),
            sweep=checks.get(
                "CRT liquidity sweep",
                False,
            ),
            reclaim=checks.get(
                "CRT close/reclaim",
                False,
            ),
            mss=checks.get(
                "M1/M5 MSS",
                False,
            ),
            engulfing=checks.get(
                "Engulfing",
                False,
            ),
            stoch=checks.get(
                "Stochastic",
                False,
            ),
            displacement=checks.get(
                "Strong displacement",
                False,
            ),
        )

    @property
    def log(self):
        return self.state.setdefault(
            "log",
            [],
        )

    def start(self):
        self.engine.start()

    def stop(self):
        self.engine.stop()
