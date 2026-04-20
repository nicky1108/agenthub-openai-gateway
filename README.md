# AgentHub OpenAI Gateway

Local-first OpenAI-compatible gateway for local agents and model providers.

Before running the app, set `ADMIN_SECRET` in your local `.env` to a unique secret that is not checked into git.

## Version 1 Scope

- `GET /v1/models`
- `POST /v1/chat/completions`
- SSE streaming
- Localhost-only admin API and admin UI

## Providers In Scope

- hermes
- codex
- gemini
- opencode

## Quick Start

Backend:

```bash
cd backend
PYTHONPATH=. ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8787
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The admin UI assumes the backend is available on the same machine and uses the local admin secret header for `/admin/*` requests.

## Smoke Checks

Health:

```bash
curl -s http://127.0.0.1:8787/healthz
```

Create an HTTP-backed provider:

```bash
curl -s -X POST http://127.0.0.1:8787/admin/providers \
  -H 'content-type: application/json' \
  -H 'x-admin-secret: change-me' \
  -d '{
    "name":"codex",
    "exposed_model":"gpt-5.4",
    "route_policy":"fixed-http",
    "http_enabled":true,
    "cli_enabled":false,
    "http_base_url":"http://127.0.0.1:9999",
    "http_headers_json":"{}",
    "cli_args_json":"[]",
    "cli_env_json":"{}"
  }'
```

List public models:

```bash
curl -s http://127.0.0.1:8787/v1/models
```

## Current Runtime Limits

The generic HTTP runtime expects an upstream that already speaks an OpenAI-compatible chat API.

The generic CLI runtime expects a command that:

- reads JSON from `stdin`
- returns JSON on `stdout`
- follows the gateway's current chat response shape

This means the gateway runtime is structurally ready for mixed HTTP/CLI providers, but real end-to-end bring-up for `hermes`, `codex`, `gemini`, and `opencode` still depends on provider-specific invocation details.

Based on current local inspection:

- `gemini` is the clearest candidate for structured CLI integration because it exposes `--output-format json` and `--output-format stream-json`
- `hermes` exposes `acp` and `mcp`
- `codex` exposes server-oriented surfaces
- `opencode` exposes `acp` and `serve`, but its help currently emits `models.dev` noise
