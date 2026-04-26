# Single-Server AgentHub Gateway Deployment

This deployment mode runs AgentHub as one gateway service on the operator's server. It does not require `agenthub-public-gateway`, reverse tunnel sessions, account sync, API key sync, or usage sync.

## Required Server Runtime

Install the local model runtimes on the server:

- Codex CLI
- Gemini CLI

The gateway process calls these CLIs from isolated provider workspaces under the configured runtime directory.

## Frontend

Default local frontend:

```text
http://127.0.0.1:3002
```

User-facing routes:

```text
GET /          public website
GET /product   product page
GET /docs      API documentation
GET /login     customer login
GET /register  customer registration
GET /portal    customer self-service portal
```

Operator route:

```text
GET /admin     operator management console
```

The customer portal and operator admin console are intentionally separate surfaces. The portal is for customer API keys, custom providers, models, usage, and API examples. The admin console is for operator-level account, credit, provider, pricing, usage, and runtime management.

## Backend

Default backend API:

```text
http://127.0.0.1:8787
```

Production env files should set explicit non-default security values:

```env
APP_ENVIRONMENT=production
ADMIN_SECRET=replace-with-a-long-random-secret
SECRET_ENCRYPTION_KEY=replace-with-a-different-32-plus-character-secret
PUBLIC_GATEWAY_SERVICE_TOKEN=replace-with-a-long-random-service-token
FRONTEND_BASE_URL=https://your-domain.example
PROVIDER_URL_STRICT_DNS=true
```

Keep admin CLI provider management disabled in production unless it is operationally required. If enabled, set `ADMIN_CLI_PROVIDER_COMMAND_ALLOWLIST_CSV` to the allowed commands, for example `codex,gemini`.

Important routes:

```text
GET  /healthz
POST /auth/register
POST /auth/login
POST /auth/logout
GET  /auth/me
GET  /portal/dashboard
GET  /portal/catalog
GET  /portal/provider-presets
GET  /portal/api-keys
POST /portal/api-keys
PATCH /portal/api-keys/{key_id}
POST /portal/api-keys/{key_id}/revoke
GET  /portal/providers
POST /portal/providers
PATCH /portal/providers/{provider_id}
DELETE /portal/providers/{provider_id}
POST /portal/providers/probe
POST /portal/providers/{provider_id}/probe
GET  /v1/models
POST /v1/chat/completions
GET  /admin/dashboard/summary
GET  /admin/usage/overview
```

User-facing OpenAI-compatible base URL:

```text
http://127.0.0.1:8787/v1
```

Example:

```bash
curl http://127.0.0.1:8787/v1/chat/completions \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "codex:gpt-5.4",
    "messages": [{"role": "user", "content": "Reply with only OK"}],
    "stream": false
  }'
```

## Custom Providers

Users can add providers from the portal/user API:

```text
GET  /portal/provider-presets
POST /portal/providers?name=minimax-cn&protocol=openai&base_url=https://api.minimaxi.com/v1&api_key=<secret>
POST /portal/providers?name=claude&protocol=anthropic&base_url=https://api.anthropic.com/v1&api_key=<secret>
```

Probe a saved provider:

```text
POST /portal/providers/{provider_id}/probe
```

Legacy `/user/api-keys` and `/user/providers` aliases are still available, but new integrations should use `/portal/*`.

After a provider is active, `/v1/models` includes custom models for that account only. Custom models use:

```text
<provider-slug>:<model-id>
```

Examples:

```text
minimax-cn:MiniMax-M2.7
claude:claude-sonnet-4-20250514
```

## Billing And Usage

Platform models such as `codex:*` and `gemini:*` use the existing local credit balance, pricing, usage records, and credit ledger.

Bring-your-own custom providers are recorded in local usage records but do not deduct local credits by default. The user's external provider bills those requests directly through the API key they configured.

## Legacy Tunnel

The reverse tunnel modules may remain in the repository as compatibility code, but this deployment mode does not require:

- `PUBLIC_GATEWAY_TUNNEL_URL`
- `PUBLIC_GATEWAY_TUNNEL_DEVICE_ID`
- `PUBLIC_GATEWAY_TUNNEL_SECRET`
- `agenthub-public-gateway`

Account, key, balance, provider, and usage state are owned by this single project database.
