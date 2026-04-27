# AgentHub OpenAI Gateway

Local-first OpenAI-compatible gateway for local model runtimes and operator-managed access control.

This project can run as a single-server AgentHub gateway. In that mode the operator installs Codex CLI and Gemini CLI on the server, and this service directly exposes the public API, user portal APIs, local admin APIs, billing, usage, and provider runtime from one database.

It also still contains legacy internal public-gateway and reverse-tunnel integration code for compatibility.

This project exposes:

- OpenAI-compatible user APIs under `/v1/*`
- a localhost-only admin control plane under `/admin/*`
- a product-style admin UI
- account, API key, credit-balance, pricing, and usage management
- local provider routing for HTTP and CLI-backed model runtimes
- user portal APIs for self-service API keys and custom providers
- internal contract routes used by legacy `agenthub-public-gateway` deployments
- a reverse-tunnel agent for legacy external public-gateway integration

## What It Does

At a high level, this gateway sits between clients and local provider runtimes.

It can:

- expose platform-managed models like `codex:*` and `gemini:*`
- expose user custom OpenAI-compatible and Anthropic-compatible providers
- proxy requests to local CLI or HTTP runtimes
- enforce API key auth and request limits
- settle usage against a local credit balance
- keep a ledger of credit adjustments and inference charges
- surface provider/model pricing in the admin UI
- let operators test models directly from the admin console

## Main Surfaces

### Frontend Routes

- `/` public website for customers
- `/product` public product page
- `/docs` customer-facing API documentation
- `/login` and `/register` customer auth
- `/portal` customer self-service portal for API keys, custom providers, models, usage, and API examples
- `/admin` operator management console for accounts, credits, providers, pricing, usage, and runtime health

### User API

- `GET /v1/models`
- `POST /v1/chat/completions`
- SSE streaming for `chat/completions`
- `POST /v1/hermes/tasks`
- `GET /v1/hermes/tasks`
- `GET /v1/hermes/tasks/{id}`
- `GET /v1/hermes/tasks/{id}/events`
- `POST /v1/hermes/tasks/{id}/cancel`

### Portal API

- `GET /portal/dashboard`
- `GET /portal/catalog`
- `GET /portal/provider-presets`
- `GET /portal/api-keys`
- `POST /portal/api-keys`
- `PATCH /portal/api-keys/{id}`
- `POST /portal/api-keys/{id}/revoke`
- `GET /portal/providers`
- `POST /portal/providers`
- `PATCH /portal/providers/{id}`
- `DELETE /portal/providers/{id}`
- `POST /portal/providers/probe`
- `POST /portal/providers/{id}/probe`

Legacy `/user/api-keys` and `/user/providers` aliases remain available for local compatibility.

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

The local machine can dial out to a public `agenthub-public-gateway` over a reverse `WSS` tunnel. This is now a legacy compatibility path for split public/local deployments. The recommended deployment is the single-server mode documented in `docs/single-server-deployment.md`.

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
- `hermes` through the long-running task API

The current project also has placeholder/admin surface support for:

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
- `codex:gpt-5.5`
- `gemini:gemini-2.5-pro`
- `gemini:gemini-2.5-flash`
- `gemini:gemini-2.5-flash-lite`
- `hermes:hermes-agent` when `HERMES_ENABLED=true`

Pricing comes from:

- official pricing snapshots when available
- manual overrides when an operator sets them

For Codex, startup sync also reads `~/.codex/models_cache.json` when present, so newly listed local Codex models can be added without a code release. Bootstrap and pricing snapshots remain as fallbacks.

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

For Hermes tasks:

- `/v1/hermes/tasks/{id}/events` replays stored events and then streams live SSE until the task reaches a terminal state
- disconnecting from the events stream does not cancel the task

## Ports

Default local ports:

- backend: `127.0.0.1:8787`
- frontend: `127.0.0.1:3002` in local single-server development, or any reverse-proxied public host in production

## Environment

At minimum, set:

- `ADMIN_SECRET`
- `SECRET_ENCRYPTION_KEY`

For production, also set:

- `APP_ENVIRONMENT=production`
- `PUBLIC_GATEWAY_SERVICE_TOKEN` to a random value, even when the public gateway tunnel is not used

For public-gateway integration, also set:

- `PUBLIC_GATEWAY_SERVICE_TOKEN`
- `PUBLIC_GATEWAY_TUNNEL_URL`
- `PUBLIC_GATEWAY_TUNNEL_DEVICE_ID`
- `PUBLIC_GATEWAY_TUNNEL_SECRET`

For server-side Hermes task execution, set:

- `HERMES_ENABLED=true`
- `HERMES_API_BASE=http://127.0.0.1:8642/v1`
- `HERMES_API_KEY=<server-side-hermes-api-key>`
- `HERMES_MODEL=hermes-agent`
- `HERMES_MAX_CONCURRENT_TASKS=2`
- `HERMES_TASK_START_CREDITS=10`
- `HERMES_TASK_RUNTIME_CREDITS_PER_MINUTE=1`

Hermes task billing uses fixed credits: 10 credits when a task is accepted, then 1 credit per rounded-up runtime minute after the task reaches a terminal state. Hermes is a sensitive platform model: it is hidden from non-admin accounts even when their platform model access mode is `all`, and admin accounts must still be explicitly granted `hermes:hermes-agent` through the admin account model visibility controls before they can call it.

Example local `.env` values for reverse-tunnel development:

```env
ADMIN_SECRET=change-me
SECRET_ENCRYPTION_KEY=local-dev-secret-encryption-key-change-before-production
PUBLIC_GATEWAY_SERVICE_TOKEN=public-gateway-dev-token-20260421
PUBLIC_GATEWAY_TUNNEL_URL=ws://127.0.0.1:8788/internal/tunnel
PUBLIC_GATEWAY_TUNNEL_DEVICE_ID=local-mac-dev
PUBLIC_GATEWAY_TUNNEL_SECRET=local-mac-dev-secret-20260421
```

## Quick Start

### Backend

```bash
cd backend
./.venv/bin/python scripts/run_backend.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 3002 --strictPort
```

## CI/CD Deployment

The recommended production deployment is GitHub Actions + SSH + systemd + Nginx.

See `docs/cicd-deployment.md` for:

- one-time server setup
- required GitHub secrets
- systemd service
- Nginx routing for `/`, `/portal`, `/admin`, `/v1`
- deployment flow from push to `main`

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

### Managed Model Web Fetch

`web_fetch` is an opt-in gateway-side tool for managed models. It only runs when the request declares the tool, and it blocks localhost, private/reserved IPs, unsupported schemes, and non-text responses.
Use a managed platform model such as `codex:gpt-5.4`; custom provider requests do not execute built-in tools.

```bash
curl -s http://127.0.0.1:8787/v1/chat/completions \
  -H 'Authorization: Bearer <API_KEY>' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "codex:gpt-5.4",
    "messages": [
      { "role": "user", "content": "Fetch https://example.com and summarize it in one sentence." }
    ],
    "stream": false,
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "web_fetch",
          "description": "Fetch a public HTTP or HTTPS URL and return readable text.",
          "parameters": {
            "type": "object",
            "properties": {
              "url": { "type": "string", "description": "Public HTTP or HTTPS URL" }
            },
            "required": ["url"]
          }
        }
      }
    ],
    "tool_choice": { "type": "function", "function": { "name": "web_fetch" } }
  }'
```

### Hermes Task API

When `HERMES_ENABLED=true`, the gateway exposes long-running Hermes agent jobs through `/v1/hermes/tasks`. Only admin accounts with an explicit `hermes:hermes-agent` platform model grant can create Hermes tasks.

Create an async task:

```bash
curl -s http://127.0.0.1:8787/v1/hermes/tasks \
  -H 'Authorization: Bearer <API_KEY>' \
  -H 'Content-Type: application/json' \
  -d '{
    "input": "帮我分析这个仓库的风险点",
    "metadata": { "source": "curl" }
  }'
```

Poll task status:

```bash
curl -s http://127.0.0.1:8787/v1/hermes/tasks/htask_example \
  -H 'Authorization: Bearer <API_KEY>'
```

List recent tasks:

```bash
curl -s 'http://127.0.0.1:8787/v1/hermes/tasks?limit=20&offset=0' \
  -H 'Authorization: Bearer <API_KEY>'
```

Stream task events:

```bash
curl -sN 'http://127.0.0.1:8787/v1/hermes/tasks/htask_example/events?after_seq=0' \
  -H 'Authorization: Bearer <API_KEY>'
```

Cancel a task:

```bash
curl -s -X POST http://127.0.0.1:8787/v1/hermes/tasks/htask_example/cancel \
  -H 'Authorization: Bearer <API_KEY>'
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
./.venv/bin/python scripts/run_tunnel_agent.py
```

These wrapper scripts enforce single-instance startup for:

- the backend on `8787`
- the tunnel agent per `device_id`

## Current Limits

- `hermes` and `opencode` are not fully brought up yet
- public-gateway reverse tunnel is phase 1 and currently limited to gateway-plane ops
- portal/session/dashboard tunnel routing is intentionally out of scope for phase 1
- Gemini model discovery is still bootstrap-augmented; Codex can additionally read the local Codex model cache

## Repository Notes

- This repo is the local control plane and local execution gateway
- The sibling `agenthub-public-gateway` repo is the externally deployed public surface
- The local repo remains the source of truth for:
  - platform-managed providers
  - operator control plane
  - local credits / ledger
  - internal public-gateway contract routes
