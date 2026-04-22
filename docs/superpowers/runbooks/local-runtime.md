# Local Runtime Runbook

Use the wrapper scripts for local startup so the gateway does not accidentally run multiple backend or tunnel-agent instances.

## Backend

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python scripts/run_backend.py
```

If another backend instance is already live, the script exits with a clear message instead of starting a second process on the same port.

## Tunnel Agent

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
PUBLIC_GATEWAY_SERVICE_TOKEN='public-gateway-dev-token-20260421' \
PUBLIC_GATEWAY_TUNNEL_URL='ws://127.0.0.1:8788/internal/tunnel' \
PUBLIC_GATEWAY_TUNNEL_DEVICE_ID='local-mac-dev' \
PUBLIC_GATEWAY_TUNNEL_SECRET='local-mac-dev-secret-20260421' \
./.venv/bin/python scripts/run_tunnel_agent.py
```

The tunnel wrapper enforces one active process per `device_id`.

## Recovery

If you suspect stale state:

```bash
pkill -f "uvicorn app.main:app --host 127.0.0.1 --port 8787" || true
pkill -f "app.tunnel.run_agent" || true
```

Then restart through the wrapper scripts above.
