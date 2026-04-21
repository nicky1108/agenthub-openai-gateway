# Public Gateway Reverse Tunnel Design

Date: 2026-04-21
Status: Approved for planning
Scope: `agenthub-public-gateway` <-> `agenthub-openai-gateway` connectivity for externally deployed gateway traffic

## 1. Problem

`agenthub-public-gateway` is intended to run on a public server, while `agenthub-openai-gateway` currently runs on a local Mac that does not have a stable public IP. The public gateway therefore cannot safely rely on direct inbound HTTP access to the local machine.

The local machine must instead create an outbound encrypted long-lived connection to the public server. That connection becomes the transport used by the public gateway to reach selected internal capabilities on the local gateway.

## 2. Goals

Phase 1 must make the public gateway able to reach the local gateway for gateway-plane operations only.

Required capabilities for phase 1:

- API key introspection
- Platform model catalog fetch
- `chat/completions` non-stream requests
- `chat/completions` stream requests
- Usage / billing event delivery

The tunnel must:

- require only outbound connectivity from the Mac
- be encrypted in transit
- support request/response and streaming response flows
- allow cancellation of in-flight streamed responses
- avoid exposing arbitrary local HTTP forwarding
- fail closed when no tunnel session is available

## 3. Non-Goals

Phase 1 does not move the full customer portal control plane through the tunnel.

Out of scope for phase 1:

- browser session bootstrap
- customer dashboard fetches
- admin UI operations
- general local network exposure
- arbitrary HTTP reverse proxying
- permanent server-side storage of operator test transcripts

The existing public-gateway code paths for `/internal/public-gateway/session` and `/internal/public-gateway/accounts/{account_id}/dashboard` remain phase-2 work for the tunnel path.

## 4. Current State

### 4.1 `agenthub-public-gateway`

The public gateway currently assumes it can reach the upstream gateway directly over HTTP.

Current examples:

- `backend/app/clients/upstream_gateway.py`
  - `POST /internal/public-gateway/introspect-key`
  - `POST /internal/public-gateway/usage-events`
- `backend/app/services/gateway_routing.py`
  - direct HTTP proxy to `/v1/chat/completions`
  - direct HTTP stream proxy to `/v1/chat/completions`
- `backend/app/services/session_service.py`
  - `GET /internal/public-gateway/session`
- `backend/app/services/portal_service.py`
  - `GET /internal/public-gateway/accounts/{account_id}/dashboard`

### 4.2 `agenthub-openai-gateway`

The local gateway currently exposes:

- public OpenAI-compatible routes under `/v1/*`
- admin routes under `/admin/*`
- no `/internal/public-gateway/*` contract yet
- no tunnel client / daemon yet

## 5. Design Summary

Use a reverse `WSS` tunnel initiated by the local gateway.

High-level shape:

1. `agenthub-public-gateway` hosts a tunnel server endpoint.
2. `agenthub-openai-gateway` runs a tunnel agent process that dials out to that endpoint.
3. The public gateway routes a small allowlisted set of internal operations over that tunnel session.
4. The local tunnel agent receives typed RPC requests and dispatches them to local gateway services on `127.0.0.1`.

The tunnel is not a generic TCP or HTTP reverse proxy. It is a typed application protocol with fixed operation names.

## 6. Architecture

### 6.1 Public Gateway Side

Add a tunnel hub inside `agenthub-public-gateway` that owns:

- current active tunnel sessions keyed by `device_id`
- connection authentication
- request multiplexing
- stream fanout to waiting HTTP clients
- tunnel heartbeat / disconnect handling

Add a new internal abstraction layer:

- `local_gateway_transport`

This abstraction decides whether to use:

- direct upstream HTTP
- or tunnel RPC

Recommended behavior:

- development mode: allow direct upstream HTTP for local testing
- production mode: prefer tunnel and fail closed when no live tunnel exists

### 6.2 Local Gateway Side

Add a dedicated tunnel agent process in `agenthub-openai-gateway`.

This agent:

- establishes the outbound `wss://...` connection
- authenticates with shared-secret-based signed handshake
- keeps heartbeats alive
- dispatches typed operations to the local gateway
- returns normal responses or stream chunks
- handles cancellation from the public server

This agent should be independent from the current FastAPI process so restart behavior stays simpler and the tunnel can reconnect without requiring a full gateway restart.

### 6.3 Local Dispatch Rule

Do not let the tunnel invoke arbitrary paths.

The local tunnel agent only supports a fixed allowlist:

- `key.introspect`
- `catalog.platform_models`
- `chat.complete`
- `usage.record`

Each operation maps to a known internal service or local HTTP endpoint.

## 7. Shared Contract

The shared contract is a typed RPC contract, not a raw HTTP tunnel.

### 7.1 Operations

#### `key.introspect`

Input:

- customer API key token

Output:

- account identity
- workspace identity
- API key identity
- status

Direct HTTP development mapping:

- `POST /internal/public-gateway/introspect-key`

#### `catalog.platform_models`

Input:

- optional locale / cache metadata only if needed later

Output:

- platform-managed model list visible to `agenthub-public-gateway`

Direct HTTP development mapping:

- `GET /internal/public-gateway/models`

#### `chat.complete`

Input:

- full OpenAI-compatible `chat/completions` request payload
- original customer API key token
- `stream: true|false`

Output:

- non-stream response object
- or stream chunks + end frame

Direct HTTP development mapping:

- `POST /v1/chat/completions` with original `Authorization: Bearer ...`

#### `usage.record`

Input:

- usage event payload produced by public gateway custom-provider execution path

Output:

- accepted / rejected

Direct HTTP development mapping:

- `POST /internal/public-gateway/usage-events`

## 8. Internal HTTP Endpoints Required on Local Gateway

Phase 1 requires these new internal routes on `agenthub-openai-gateway`:

- `POST /internal/public-gateway/introspect-key`
- `GET /internal/public-gateway/models`
- `POST /internal/public-gateway/usage-events`

It can continue to reuse the existing:

- `POST /v1/chat/completions`

These internal routes must require a dedicated service token separate from customer API keys and separate from the admin secret.

Recommended auth header:

- `x-public-gateway-token`

## 9. Tunnel Protocol

Use JSON envelopes over a single authenticated WebSocket.

### 9.1 Envelope Shape

Every frame should contain:

- `type`
- `request_id` when request-scoped
- `device_id`
- `payload`

### 9.2 Frame Types

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

### 9.3 Request Flow

Non-stream:

1. public gateway sends `request`
2. local tunnel agent performs dispatch
3. local tunnel agent sends `response_start`
4. local tunnel agent sends `response_end`

Stream:

1. public gateway sends `request`
2. local tunnel agent starts local streamed completion
3. local tunnel agent sends `response_start`
4. zero or more `response_chunk`
5. `response_end`

Cancellation:

1. external HTTP client disconnects or times out
2. public gateway sends `cancel`
3. local tunnel agent aborts local in-flight request if possible

## 10. Authentication and Security

### 10.1 Transport

- `WSS` only
- no plaintext mode in production

### 10.2 Handshake

The tunnel agent sends a signed `hello` containing:

- `device_id`
- `timestamp`
- `nonce`
- `signature`

Signature:

- `HMAC-SHA256(shared_secret, canonical_payload)`

The server validates:

- known `device_id`
- timestamp freshness
- nonce replay protection
- signature match

### 10.3 Session Policy

- only one active session per `device_id`
- new session replaces old session
- requests fail closed if no authenticated tunnel session exists

### 10.4 Scope Restriction

Do not allow:

- arbitrary host forwarding
- arbitrary path forwarding
- arbitrary request headers from public gateway into local machine

Only typed allowlisted operations may cross the tunnel.

## 11. Failure Semantics

### 11.1 No Tunnel

When production tunnel mode is required and no live session exists:

- model catalog fetch returns `503`
- platform model chat returns `503`
- introspection returns `503`
- usage event path returns retryable failure

### 11.2 Mid-Stream Failure

If the local tunnel drops during a stream:

- public gateway emits a terminal error to the waiting client
- request is marked failed
- partial chunks already sent remain sent

### 11.3 Reconnect

Tunnel agent reconnect policy:

- immediate retry for first few failures
- exponential backoff with cap
- heartbeat timeout resets session state on the server

## 12. Implementation Plan Shape

Recommended sequence:

1. Add internal service contract routes to `agenthub-openai-gateway`
2. Add typed tunnel protocol types and tunnel server to `agenthub-public-gateway`
3. Add tunnel agent process to `agenthub-openai-gateway`
4. Add transport abstraction in `agenthub-public-gateway` that can use direct HTTP or tunnel
5. Move `introspect-key`, `models`, `chat`, and `usage-events` through the abstraction
6. Add integration tests for non-stream and stream tunnel paths

## 13. Testing Strategy

Minimum verification for phase 1:

- unit test for tunnel handshake validation
- unit test for typed request multiplexing
- integration test for `key.introspect` over tunnel
- integration test for `catalog.platform_models` over tunnel
- integration test for non-stream `chat.complete` over tunnel
- integration test for stream `chat.complete` over tunnel
- integration test for `usage.record` over tunnel
- reconnect test after server-side disconnect
- cancel test for streamed request cancellation

## 14. Risks

### 14.1 Incomplete Current Upstream Contract

`agenthub-public-gateway` already expects internal upstream routes, but `agenthub-openai-gateway` does not yet implement them. This mismatch must be fixed before the tunnel can be useful.

### 14.2 Portal vs Gateway Scope Creep

The public gateway also has portal/session service code that assumes direct upstream connectivity. Pulling all of that into the tunnel now would slow the main goal. Phase 1 must stay gateway-plane only.

### 14.3 Streaming Complexity

Streaming is the hardest part of the tunnel. The protocol must keep chunk ordering, end-of-stream signaling, and cancellation explicit.

## 15. Decisions

- Use reverse outbound `WSS`, not inbound HTTP exposure.
- Use typed RPC, not raw reverse HTTP proxying.
- First phase supports gateway-plane only.
- Keep development direct-HTTP fallback available.
- Add dedicated `/internal/public-gateway/*` routes on the local gateway for non-chat contract operations.
