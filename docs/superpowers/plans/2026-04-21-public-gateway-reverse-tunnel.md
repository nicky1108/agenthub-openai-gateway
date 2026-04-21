# Public Gateway Reverse Tunnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect `agenthub-public-gateway` to the local `agenthub-openai-gateway` through an outbound reverse `WSS` tunnel so the public server can perform platform-model gateway operations without needing inbound access to the Mac.

**Architecture:** Add a typed `/internal/public-gateway/*` contract on the local gateway, a tunnel server and transport abstraction on the public gateway, and a dedicated local tunnel agent that dials out and dispatches allowlisted operations. Keep phase 1 limited to gateway-plane operations: key introspection, platform model catalog, non-stream/stream `chat/completions`, and usage-event delivery.

**Tech Stack:** FastAPI, SQLAlchemy, `websockets`, `httpx`, asyncio tasks, Pydantic, pytest, pytest-asyncio.

---

## File Map

### `agenthub-openai-gateway`

- Create: `backend/app/api/internal_public_gateway.py`
- Create: `backend/app/services/public_gateway_contract.py`
- Create: `backend/app/tunnel/agent.py`
- Create: `backend/app/tunnel/protocol.py`
- Create: `backend/tests/test_internal_public_gateway.py`
- Create: `backend/tests/test_tunnel_agent.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/settings.py`
- Modify: `backend/pyproject.toml`

### `agenthub-public-gateway`

- Create: `backend/app/api/tunnel.py`
- Create: `backend/app/tunnel/hub.py`
- Create: `backend/app/tunnel/protocol.py`
- Create: `backend/app/services/local_gateway_transport.py`
- Create: `backend/tests/test_tunnel_server.py`
- Create: `backend/tests/test_local_gateway_transport.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/settings.py`
- Modify: `backend/app/clients/upstream_gateway.py`
- Modify: `backend/app/services/gateway_routing.py`
- Modify: `backend/app/auth/service.py`
- Modify: `backend/tests/test_gateway_auth.py`
- Modify: `backend/tests/test_gateway_platform_route.py`
- Modify: `backend/tests/test_upstream_client.py`

## Cross-Repo Constraints

- Phase 1 does **not** route portal/session/dashboard reads through tunnel.
- `agenthub-public-gateway` currently assumes direct upstream HTTP for:
  - `/internal/public-gateway/introspect-key`
  - `/internal/public-gateway/usage-events`
  - `/v1/chat/completions`
- `agenthub-public-gateway` also references:
  - `/internal/public-gateway/session`
  - `/internal/public-gateway/accounts/{account_id}/dashboard`
  Those remain phase-2 and must not be dragged into phase-1 tunnel delivery.
- The public-gateway directory is not currently a git repository, so commit steps only apply to `agenthub-openai-gateway` unless that changes later.

## Task 1: Add the Local Internal Contract

**Files:**
- Create: `agenthub-openai-gateway/backend/app/api/internal_public_gateway.py`
- Create: `agenthub-openai-gateway/backend/app/services/public_gateway_contract.py`
- Modify: `agenthub-openai-gateway/backend/app/main.py`
- Modify: `agenthub-openai-gateway/backend/app/core/settings.py`
- Test: `agenthub-openai-gateway/backend/tests/test_internal_public_gateway.py`

- [ ] **Step 1: Write the failing contract tests**

Cover these routes:

- `POST /internal/public-gateway/introspect-key`
- `GET /internal/public-gateway/models`
- `POST /internal/public-gateway/usage-events`

Test assertions:

- service token is required via `x-public-gateway-token`
- introspection returns `account_id`, `workspace_id`, `api_key_id`, `status`
- models route returns only platform-facing models needed by the public gateway
- usage-events accepts non-billable custom-provider usage payloads and persists them

- [ ] **Step 2: Run tests to confirm failure**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
./backend/.venv/bin/python -m pytest -q backend/tests/test_internal_public_gateway.py
```

Expected:

- missing module / missing route failures

- [ ] **Step 3: Add settings for the service token**

Modify `backend/app/core/settings.py` to add:

- `public_gateway_service_token`
- optional `public_gateway_tunnel_device_id`
- optional `public_gateway_tunnel_secret`

Keep this token separate from:

- admin secret
- customer API keys

- [ ] **Step 4: Implement contract service**

Create `backend/app/services/public_gateway_contract.py` with small typed helpers:

- `introspect_api_key(token)`
- `list_platform_models(session)`
- `record_usage_event(session, payload)`

Do not bury logic inside route handlers.

- [ ] **Step 5: Implement internal routes**

Create `backend/app/api/internal_public_gateway.py` and wire it into `backend/app/main.py`.

Route rules:

- fail `401` on missing/invalid service token
- keep payloads small and typed
- no admin-secret fallback

- [ ] **Step 6: Run tests**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
./backend/.venv/bin/python -m pytest -q backend/tests/test_internal_public_gateway.py
```

Expected:

- PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/nicky/agenthub-openai-gateway
git add backend/app/api/internal_public_gateway.py backend/app/services/public_gateway_contract.py backend/app/main.py backend/app/core/settings.py backend/tests/test_internal_public_gateway.py backend/pyproject.toml
git commit -m "Define internal public-gateway contract" -m "Constraint: Service-token-only internal routes must remain separate from admin and customer auth." -m "Rejected: Reuse admin endpoints | wrong trust boundary for a public-facing gateway peer." -m "Confidence: high" -m "Scope-risk: moderate" -m "Directive: Keep portal/session contract out of phase-1 internal routes." -m "Tested: backend/tests/test_internal_public_gateway.py"
```

## Task 2: Add Tunnel Protocol Types on Both Sides

**Files:**
- Create: `agenthub-openai-gateway/backend/app/tunnel/protocol.py`
- Create: `agenthub-public-gateway/backend/app/tunnel/protocol.py`

- [ ] **Step 1: Write the protocol as code, not prose**

Define typed envelopes for:

- `hello`
- `hello_ack`
- `ping`
- `pong`
- `request`
- `response_start`
- `response_chunk`
- `response_end`
- `response_error`
- `cancel`

Each request-scoped envelope must include:

- `request_id`
- `op`
- `device_id`
- `payload`

- [ ] **Step 2: Keep protocol payloads minimal**

Allowlisted ops only:

- `key.introspect`
- `catalog.platform_models`
- `chat.complete`
- `usage.record`

- [ ] **Step 3: Add protocol unit tests where useful**

At minimum validate:

- envelope parsing
- required field presence
- op name validation

## Task 3: Add Tunnel Server to `agenthub-public-gateway`

**Files:**
- Create: `agenthub-public-gateway/backend/app/api/tunnel.py`
- Create: `agenthub-public-gateway/backend/app/tunnel/hub.py`
- Modify: `agenthub-public-gateway/backend/app/main.py`
- Modify: `agenthub-public-gateway/backend/app/core/settings.py`
- Test: `agenthub-public-gateway/backend/tests/test_tunnel_server.py`

- [ ] **Step 1: Write failing tunnel server tests**

Cover:

- valid `hello` establishes authenticated session
- second session for same `device_id` replaces the first
- invalid signature rejected
- `request_id` correlation maintained
- `cancel` is forwarded to active request channel

- [ ] **Step 2: Add settings**

Add public-gateway-side tunnel settings:

- `public_tunnel_bind_path` or route path
- `public_gateway_known_devices_json`
- handshake freshness and heartbeat timing knobs
- direct-HTTP fallback mode flag

- [ ] **Step 3: Implement tunnel hub**

`backend/app/tunnel/hub.py` should own:

- active session registry by `device_id`
- in-flight request futures / queues
- heartbeat tracking
- request multiplexer

- [ ] **Step 4: Implement authenticated WebSocket endpoint**

`backend/app/api/tunnel.py` should:

- accept `WSS` upgrade
- validate `hello`
- attach the session to the hub
- run read/write loop until disconnect

- [ ] **Step 5: Run tunnel server tests**

Run:

```bash
cd /Users/nicky/agenthub-public-gateway/backend
./.venv/bin/python -m pytest -q tests/test_tunnel_server.py
```

Expected:

- PASS

## Task 4: Add the Local Tunnel Agent

**Files:**
- Create: `agenthub-openai-gateway/backend/app/tunnel/agent.py`
- Modify: `agenthub-openai-gateway/backend/app/core/settings.py`
- Test: `agenthub-openai-gateway/backend/tests/test_tunnel_agent.py`

- [ ] **Step 1: Write failing tunnel-agent tests**

Cover:

- outbound connect with signed `hello`
- request dispatch for `key.introspect`
- request dispatch for `catalog.platform_models`
- non-stream `chat.complete`
- stream `chat.complete`
- `cancel` interrupts active streamed request

- [ ] **Step 2: Implement the tunnel agent**

The agent should:

- open outbound `wss://...`
- send signed handshake
- keep ping/pong alive
- dispatch incoming typed operations
- emit `response_start`, `response_chunk`, `response_end`, `response_error`

- [ ] **Step 3: Keep local dispatch typed**

Do not directly forward arbitrary URLs. The agent must map ops to:

- internal service functions for `key.introspect`, `catalog.platform_models`, `usage.record`
- existing `/v1/chat/completions` path or orchestrator path for `chat.complete`

- [ ] **Step 4: Run tests**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
./backend/.venv/bin/python -m pytest -q backend/tests/test_tunnel_agent.py
```

Expected:

- PASS

## Task 5: Add a Public-Gateway Transport Abstraction

**Files:**
- Create: `agenthub-public-gateway/backend/app/services/local_gateway_transport.py`
- Modify: `agenthub-public-gateway/backend/app/clients/upstream_gateway.py`
- Modify: `agenthub-public-gateway/backend/app/services/gateway_routing.py`
- Modify: `agenthub-public-gateway/backend/app/auth/service.py`
- Test: `agenthub-public-gateway/backend/tests/test_local_gateway_transport.py`
- Modify: `agenthub-public-gateway/backend/tests/test_gateway_auth.py`
- Modify: `agenthub-public-gateway/backend/tests/test_gateway_platform_route.py`
- Modify: `agenthub-public-gateway/backend/tests/test_upstream_client.py`

- [ ] **Step 1: Write failing transport tests**

Cover:

- tunnel-first introspection
- tunnel-first model catalog
- tunnel-first non-stream chat
- tunnel-first stream chat
- tunnel unavailable -> `503` in production mode
- direct HTTP fallback still works in development mode

- [ ] **Step 2: Implement the abstraction**

`local_gateway_transport.py` should expose:

- `introspect_api_key(...)`
- `list_platform_models(...)`
- `chat_complete(...)`
- `chat_complete_stream(...)`
- `record_usage_event(...)`

It decides between:

- direct HTTP
- tunnel RPC

- [ ] **Step 3: Refactor existing direct callers**

Move these call sites onto the abstraction:

- `auth/service.py`
- `services/gateway_routing.py`
- `clients/upstream_gateway.py` or thin it down if it becomes an HTTP fallback-only client

- [ ] **Step 4: Keep portal/session calls out**

Do not reroute:

- `/internal/public-gateway/session`
- `/internal/public-gateway/accounts/{account_id}/dashboard`

Those remain phase 2.

- [ ] **Step 5: Run tests**

Run:

```bash
cd /Users/nicky/agenthub-public-gateway/backend
./.venv/bin/python -m pytest -q tests/test_gateway_auth.py tests/test_gateway_platform_route.py tests/test_upstream_client.py tests/test_local_gateway_transport.py
```

Expected:

- PASS

## Task 6: Wire Usage Events Through the New Contract

**Files:**
- Modify: `agenthub-public-gateway/backend/app/services/custom_provider_runtime.py`
- Modify: `agenthub-public-gateway/backend/tests/test_gateway_custom_route.py`

- [ ] **Step 1: Move usage event delivery to the transport abstraction**

Current custom-provider completion path posts directly upstream. Replace that with the new abstraction so production mode can use tunnel delivery.

- [ ] **Step 2: Verify non-billable semantics remain unchanged**

Ensure custom-provider usage still reports:

- `billable: false`
- `credits_delta: 0`

and does not break customer completion on usage-report failure.

- [ ] **Step 3: Run tests**

Run:

```bash
cd /Users/nicky/agenthub-public-gateway/backend
./.venv/bin/python -m pytest -q tests/test_gateway_custom_route.py
```

Expected:

- PASS

## Task 7: End-to-End Tunnel Integration Tests

**Files:**
- Create: `agenthub-openai-gateway/backend/tests/test_public_gateway_tunnel_integration.py`
- Create or modify: `agenthub-public-gateway/backend/tests/test_tunnel_server.py`

- [ ] **Step 1: Create in-process integration harness**

Spin up:

- public-gateway tunnel server
- local tunnel agent
- local gateway app

Use test transports or in-process async tasks to avoid real internet dependency.

- [ ] **Step 2: Verify these flows**

- introspection over tunnel
- models fetch over tunnel
- non-stream platform chat over tunnel
- stream platform chat over tunnel
- cancel streamed request over tunnel
- usage-event over tunnel

- [ ] **Step 3: Run integration tests**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
./backend/.venv/bin/python -m pytest -q backend/tests/test_public_gateway_tunnel_integration.py
```

and

```bash
cd /Users/nicky/agenthub-public-gateway/backend
./.venv/bin/python -m pytest -q tests/test_tunnel_server.py tests/test_local_gateway_transport.py
```

Expected:

- PASS

## Task 8: Runbook and Local Smoke

**Files:**
- Create: `agenthub-openai-gateway/docs/superpowers/runbooks/public-gateway-tunnel-smoke.md`
- Optionally create: `agenthub-public-gateway/docs/superpowers/runbooks/reverse-tunnel-smoke.md`

- [ ] **Step 1: Document startup order**

Document:

1. start local gateway
2. start public gateway
3. start local tunnel agent
4. verify tunnel session health

- [ ] **Step 2: Document smoke checks**

Smoke commands should verify:

- tunnel session established
- public gateway can introspect a key
- public gateway can fetch platform models
- public gateway can complete a non-stream chat
- public gateway can complete a stream chat

- [ ] **Step 3: Final verification sweep**

Run the relevant backend test suites in both repos plus one manual smoke run.

## Spec Coverage Check

Covered requirements from the approved spec:

- outbound encrypted long-lived connection
- typed RPC protocol
- allowlisted operation scope
- phase-1 gateway-plane-only boundary
- non-stream and stream completion support
- usage event return path
- cancel support
- fail-closed behavior

Known intentional omissions for this phase:

- portal session tunnel routing
- dashboard tunnel routing
- admin UI tunnel routing

