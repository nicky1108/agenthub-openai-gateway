# Persistent CLI Runtime Design

Date: 2026-04-23
Status: Spike approved
Scope: local performance path for CLI-backed providers

## 1. Problem

The gateway still pays a large latency cost on CLI-backed requests even after adapter/config reuse was added.

Recent runtime measurements show:

- `spawn` itself is negligible, around `1ms`
- the dominant delay is between process start and useful provider output

Measured on local runtime:

### `codex:gpt-5.4`

- non-stream
  - `gateway.cli.spawn`: about `1ms`
  - `gateway.cli.first_output`: about `234ms`
  - `gateway.cli.complete`: about `15.2s`
- stream
  - `gateway.cli.spawn`: under `1ms`
  - `gateway.cli.first_output`: about `171ms`
  - first gateway-visible chunk: about `9.2s`
  - `gateway.cli.complete`: about `11.1s`

### `gemini:gemini-2.5-flash`

- non-stream
  - `gateway.cli.spawn`: under `1ms`
  - `gateway.cli.first_output`: about `14.7s`
  - `gateway.cli.complete`: about `14.7s`
- stream
  - `gateway.cli.spawn`: about `1ms`
  - `gateway.cli.first_output`: about `10.4s`
  - first gateway-visible chunk: about `12.8s`
  - `gateway.cli.complete`: about `12.9s`

This means the current optimization target is not Python-side orchestration or subprocess creation. The target is the CLI runtime lifecycle itself.

## 2. Findings

### 2.1 `codex exec-server`

`codex exec-server` exposes a `--listen ws://...` flag and prints a socket URL, but local probing shows that it does not accept a standard websocket handshake.

Observed behavior:

- server prints `ws://127.0.0.1:<port>`
- standard websocket clients fail with:
  - `InvalidMessage did not receive a valid HTTP response`

Conclusion:

- `codex exec-server` is promising, but its transport is not yet transparent enough for a safe first integration
- it needs a dedicated protocol investigation before it can be wired into the gateway

### 2.2 `gemini --acp`

Local bundle inspection and live probing show that Gemini ACP is much better understood:

- transport is stdio
- framing is newline-delimited JSON
- request format is JSON-RPC 2.0
- agent methods include:
  - `initialize`
  - `session/new`
  - `session/prompt`
  - `session/cancel`

Live probe succeeded with:

1. `initialize`
2. `session/new`
3. `session/prompt`

And returned:

- session creation metadata
- model/mode catalog
- streamed `session/update` events
- final `session/prompt` result

Conclusion:

- Gemini ACP is the safest first path for a persistent runtime spike

## 3. Decision

Phase 1 of persistent runtime work should target Gemini only.

Do not change Codex request execution yet.

Instead:

1. build an isolated Gemini ACP client in the backend
2. verify that it can:
   - start the process
   - initialize
   - create a session
   - send a prompt
   - consume streamed updates
   - close cleanly
3. keep it out of the production request path until correctness and failure behavior are understood

## 4. Phase 1 Spike Shape

Add a small runtime client module that owns:

- the `gemini --acp` child process
- stdio JSON-RPC transport
- request id generation
- session creation and reuse

The spike should support:

- `initialize()`
- `new_session(cwd)`
- `prompt(session_id, text)`
- graceful shutdown

The first spike can be single-session and single-flight.

That keeps the design narrow and avoids concurrency bugs before the protocol behavior is stable.

## 5. Non-Goals for the Spike

Do not:

- change `/v1/chat/completions` yet
- replace the current Gemini CLI adapter yet
- add Codex persistent runtime support yet
- add multi-session pooling yet
- add persistence across gateway restarts yet

## 6. Risks

- ACP prompt behavior may depend on environment/auth state that differs from the current headless CLI path
- session updates may include richer event types than the current gateway stream model expects
- cancellation semantics need separate validation before request-path integration
- long-lived Gemini sessions may have their own memory growth or stale-session behavior

## 7. Next Step

Implement the isolated Gemini ACP client plus tests, without wiring it into the live gateway path.
