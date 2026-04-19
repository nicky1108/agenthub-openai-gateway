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
