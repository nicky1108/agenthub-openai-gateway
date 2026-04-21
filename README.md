# AgentHub OpenAI Gateway

Local-first OpenAI-compatible gateway for local model runtimes and operator-managed access control.

This project runs on a local machine and exposes:

- OpenAI-compatible user APIs under `/v1/*`
- a localhost-only admin control plane under `/admin/*`
- a product-style admin UI
- account, API key, credit-balance, pricing, and usage management
- local provider routing for HTTP and CLI-backed model runtimes
- internal contract routes used by `agenthub-public-gateway`
- a reverse-tunnel agent for external public-gateway integration

## What It Does

At a high level, this gateway sits between clients and local provider runtimes.

It can:

- expose platform-managed models like `codex:*` and `gemini:*`
- proxy requests to local CLI or HTTP runtimes
- enforce API key auth and request limits
- settle usage against a local credit balance
- keep a ledger of credit adjustments and inference charges
- surface provider/model pricing in the admin UI
- let operators test models directly from the admin console

## Main Surfaces

### User API

- `GET /v1/models`
- `POST /v1/chat/completions`
- SSE streaming for `chat/completions`

### Admin API

- `GET /healthz`
- `GET /admin/providers`
- `GET /admin/providers/{name}/models`
- `POST /admin/providers`
- `POST /admin/providers/{name}/rediscover`
- `PATCH /admin/providers/{name}/models/{native_model}`
- `PATCH /admin/providers/{name}/models/{native_model}/pricing`
- `POST /admin/accounts`
- `POST /admin/accounts/{account_id}/credits/adjust`
- `GET /admin/accounts/{account_id}/credits/ledger`
- `POST /admin/api-keys`
- `POST /admin/api-keys/{id}/revoke`
- `GET /admin/dashboard/summary`
- `GET /admin/dashboard/timeseries`
- `GET /admin/settings/overview`
- `POST /admin/test-chat`

### Internal Public-Gateway Contract

These routes are for the sibling public gateway and are protected by `x-public-gateway-token`:

- `POST /internal/public-gateway/introspect-key`
- `GET /internal/public-gateway/models`
- `POST /internal/public-gateway/usage-events`

### Reverse Tunnel Agent

The local machine can dial out to a public `agenthub-public-gateway` over a reverse `WSS` tunnel.

Supported typed ops:

- `key.introspect`
- `catalog.platform_models`
- `chat.complete`
- `usage.record`

The local tunnel agent entrypoint is:

```bash
cd backend
./.venv/bin/python -m app.tunnel.run_agent
```

## Current Local Providers

The gateway currently has real local support for:

- `codex`
- `gemini`

The current project also has placeholder/admin surface support for:

- `hermes`
- `opencode`

Those two are not fully brought up yet.

## Credits and Billing

The gateway uses local credit accounting:

- `1 USD = 100 credits`
- each inference charge is settled from pricing snapshots plus usage
- balances live on accounts
- every credit change is recorded in `credit_ledger`

Billing behavior:

- zero or insufficient balance rejects requests with `402`
- successful requests create a `model_inference` ledger entry
- manual adjustments create `manual_adjustment` ledger entries

## Model Catalog and Pricing

The model catalog is provider-scoped and exposed publicly as `provider:model`.

Examples:

- `codex:gpt-5.4`
- `codex:gpt-5.4-mini`
- `codex:gpt-5.4-nano`
- `gemini:gemini-2.5-pro`
- `gemini:gemini-2.5-flash`
- `gemini:gemini-2.5-flash-lite`

Pricing comes from:

- official pricing snapshots when available
- manual overrides when an operator sets them

The admin UI displays:

- exposed model ID
- source / status
- official or overridden pricing
- sync time
- validation console transcript

## Streaming Behavior

The gateway itself serves real SSE for:

- `/v1/chat/completions`
- `/admin/test-chat` when `stream=true`

For CLI-backed providers:

- `codex` and `gemini` now stream by incrementally reading CLI stdout
- the external chunk cadence still depends on the upstream CLI's own output granularity

## Ports

Default local ports:

- backend: `127.0.0.1:8787`
- frontend: `127.0.0.1:3000`

## Environment

At minimum, set:

- `ADMIN_SECRET`

For public-gateway integration, also set:

- `PUBLIC_GATEWAY_SERVICE_TOKEN`
- `PUBLIC_GATEWAY_TUNNEL_URL`
- `PUBLIC_GATEWAY_TUNNEL_DEVICE_ID`
- `PUBLIC_GATEWAY_TUNNEL_SECRET`

Example local `.env` values for reverse-tunnel development:

```env
ADMIN_SECRET=change-me
PUBLIC_GATEWAY_SERVICE_TOKEN=public-gateway-dev-token-20260421
PUBLIC_GATEWAY_TUNNEL_URL=ws://127.0.0.1:8788/internal/tunnel
PUBLIC_GATEWAY_TUNNEL_DEVICE_ID=local-mac-dev
PUBLIC_GATEWAY_TUNNEL_SECRET=local-mac-dev-secret-20260421
```

## Quick Start

### Backend

```bash
cd backend
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8787
```

### Frontend

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 3000
```

## Basic User API Checks

### List Models

```bash
curl -s http://127.0.0.1:8787/v1/models \
  -H 'Authorization: Bearer <API_KEY>'
```

### Non-Streaming Chat

```bash
curl -s http://127.0.0.1:8787/v1/chat/completions \
  -H 'Authorization: Bearer <API_KEY>' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "codex:gpt-5.4",
    "messages": [
      { "role": "user", "content": "Say OK and nothing else." }
    ],
    "stream": false
  }'
```

### Streaming Chat

```bash
curl -sN http://127.0.0.1:8787/v1/chat/completions \
  -H 'Authorization: Bearer <API_KEY>' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "codex:gpt-5.4",
    "messages": [
      { "role": "user", "content": "Say OK and nothing else." }
    ],
    "stream": true
  }'
```

## Basic Admin Checks

### Health

```bash
curl -s http://127.0.0.1:8787/healthz
```

### List Providers

```bash
curl -s http://127.0.0.1:8787/admin/providers \
  -H 'x-admin-secret: change-me'
```

### List Provider Models

```bash
curl -s http://127.0.0.1:8787/admin/providers/codex/models \
  -H 'x-admin-secret: change-me'
```

### Test a Model from Admin

```bash
curl -s http://127.0.0.1:8787/admin/test-chat \
  -H 'x-admin-secret: change-me' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "codex:gpt-5.4",
    "messages": [
      { "role": "user", "content": "Say OK and nothing else." }
    ]
  }'
```

### Stream a Model from Admin

```bash
curl -sN http://127.0.0.1:8787/admin/test-chat \
  -H 'x-admin-secret: change-me' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "codex:gpt-5.4",
    "messages": [
      { "role": "user", "content": "Say OK and nothing else." }
    ],
    "stream": true
  }'
```

## Reverse-Tunnel Local Dev

If `agenthub-public-gateway` is running locally on `127.0.0.1:8788`, start the local tunnel agent with:

```bash
cd backend
PUBLIC_GATEWAY_SERVICE_TOKEN='public-gateway-dev-token-20260421' \
PUBLIC_GATEWAY_TUNNEL_URL='ws://127.0.0.1:8788/internal/tunnel' \
PUBLIC_GATEWAY_TUNNEL_DEVICE_ID='local-mac-dev' \
PUBLIC_GATEWAY_TUNNEL_SECRET='local-mac-dev-secret-20260421' \
./.venv/bin/python -m app.tunnel.run_agent
```

## Current Limits

- `hermes` and `opencode` are not fully brought up yet
- public-gateway reverse tunnel is phase 1 and currently limited to gateway-plane ops
- portal/session/dashboard tunnel routing is intentionally out of scope for phase 1
- some provider model catalogs are still bootstrap-augmented rather than fully discovered from the provider CLI itself

## Repository Notes

- This repo is the local control plane and local execution gateway
- The sibling `agenthub-public-gateway` repo is the externally deployed public surface
- The local repo remains the source of truth for:
  - platform-managed providers
  - operator control plane
  - local credits / ledger
  - internal public-gateway contract routes
