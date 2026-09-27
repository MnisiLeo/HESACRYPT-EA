import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from trading_engine.engine import Engine


app = FastAPI(
    title="L.Mnisi EA API",
    version="2.1",
)

engine = Engine()

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
FRONTEND = PROJECT / "frontend"
ASSETS = FRONTEND / "assets"

API_KEY = os.getenv(
    "LMNISI_API_KEY",
    "",
).strip()


def auth(x_api_key: str | None):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )


class Action(BaseModel):
    action: str
    mode: str | None = None
    symbol: str | None = None
    lot: float | None = Field(
        default=None,
        gt=0,
        le=100,
    )


if ASSETS.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(ASSETS)),
        name="assets",
    )


@app.get("/")
def home():
    return FileResponse(
        FRONTEND / "index.html"
    )


@app.get("/manifest.json")
def manifest():
    return FileResponse(
        FRONTEND / "manifest.json"
    )


@app.get("/sw.js")
def service_worker():
    return FileResponse(
        FRONTEND / "sw.js"
    )


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "service": "LMnisi",
        "api_online": True,
        "metaapi_configured": (
            engine.api.configured
        ),
        "metaapi_connected": (
            engine.api.ready()
        ),
        "engine_running": (
            engine.running
        ),
        "status": engine.state.get(
            "status",
            "READY",
        ),
    }


@app.get("/api/status")
def status(
    x_api_key: str | None = Header(
        default=None,
    ),
):
    auth(x_api_key)

    positions = []

    if engine.api.ready():
        try:
            positions = engine.api.positions()
        except Exception as exc:
            engine.state["last_error"] = str(
                exc
            )[:500]

    state = engine.state
    signal = engine.last

    return {
        "ok": True,
        "api_online": True,
        "connected": engine.api.ready(),
        "metaapi_configured": (
            engine.api.configured
        ),
        "running": engine.running,
        "status": state.get(
            "status",
            "READY",
        ),
        "mode": engine.mode,
        "symbol": engine.symbol,
        "pair": engine.symbol,
        "lot": engine.lot,
        "balance": state.get(
            "balance"
        ),
        "equity": state.get(
            "equity"
        ),
        "account_type": state.get(
            "account_type",
            "",
        ),
        "server": state.get(
            "server",
            "",
        ),
        "broker": state.get(
            "broker",
            "",
        ),
        "score": getattr(
            signal,
            "score",
            0,
        ),
        "max_score": 22,
        "signal": getattr(
            signal,
            "side",
            "WAIT",
        ),
        "raw_side": state.get(
            "raw_side",
            "WAIT",
        ),
        "reason": getattr(
            signal,
            "reason",
            state.get(
                "reason",
                "Waiting",
            ),
        ),
        "qualified": state.get(
            "qualified",
            False,
        ),
        "execution_status": state.get(
            "execution_status",
            "IDLE",
        ),
        "bias": getattr(
            signal,
            "bias",
            False,
        ),
        "sweep": getattr(
            signal,
            "sweep",
            False,
        ),
        "reclaim": getattr(
            signal,
            "reclaim",
            False,
        ),
        "mss": getattr(
            signal,
            "mss",
            False,
        ),
        "engulfing": getattr(
            signal,
            "engulfing",
            False,
        ),
        "stoch": getattr(
            signal,
            "stoch",
            False,
        ),
        "displacement": getattr(
            signal,
            "displacement",
            False,
        ),
        "checks": state.get(
            "checks",
            {},
        ),
        "stochastic": state.get(
            "stochastic",
        ),
        "entry": state.get(
            "entry",
        ),
        "market_time": state.get(
            "market_time",
        ),
        "last_update": state.get(
            "last_update",
        ),
        "last_error": state.get(
            "last_error",
            "",
        ),
        "positions": positions,
        "log": engine.log[-30:],
    }


@app.post("/api/control")
def control(
    action: Action,
    x_api_key: str | None = Header(
        default=None,
    ),
):
    auth(x_api_key)

    try:
        if action.symbol is not None:
            engine.symbol = action.symbol

        if action.lot is not None:
            engine.lot = action.lot

        command = (
            action.action or ""
        ).strip().lower()

        if command == "start":
            engine.start()

        elif command == "stop":
            engine.stop()

        elif command == "mode":
            if action.mode not in (
                "demo",
                "live",
            ):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "mode must be demo or live"
                    ),
                )

            engine.mode = action.mode

        elif command == "settings":
            # Symbol and lot have already been
            # applied above.
            pass

        else:
            raise HTTPException(
                status_code=400,
                detail="Unknown action",
            )

        return status(x_api_key)

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        engine.state["last_error"] = str(
            exc
        )[:500]

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@app.post("/api/close-all")
def close_all(
    x_api_key: str | None = Header(
        default=None,
    ),
):
    auth(x_api_key)

    if not engine.api.ready():
        return {
            "ok": False,
            "message": (
                "MetaApi is not connected."
            ),
            "closed": [],
            **status(x_api_key),
        }

    try:
        positions = engine.api.positions()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    closed = []
    errors = []

    for position in positions:
        position_id = position.get("id")

        if not position_id:
            continue

        try:
            closed.append(
                engine.api.close_position(
                    position_id
                )
            )
        except Exception as exc:
            errors.append(
                {
                    "id": position_id,
                    "error": str(exc),
                }
            )

    return {
        "ok": not errors,
        "closed": closed,
        "errors": errors,
        **status(x_api_key),
    }
