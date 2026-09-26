# Render deployment checklist

1. Put every file at the repository root. `Dockerfile`, `requirements.txt`, `render.yaml`, `backend/`, `strategy/`, `trading_engine/`, and `web/` must be at the root.
2. In Render choose Docker, branch `main`, leave Root Directory blank.
3. Add the environment variables from `.env.example`.
4. Keep `ALLOW_LIVE_TRADING=false` while connecting/testing a demo account.
5. After deployment open `/api/health` on the Render URL. `metaapi_configured` should become true only after token/account ID are supplied; `connected` becomes true after the broker account is reachable.
6. Set the web UI API address to the Render URL only if the UI is hosted separately. When served by this same service, it defaults to its own URL.
