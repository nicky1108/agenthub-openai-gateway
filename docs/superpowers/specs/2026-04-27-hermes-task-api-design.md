# Hermes Task API Design

## Goal

Expose the Hermes service deployed on the gateway server as a first-class long-running task API.

The primary integration surface is a dedicated `/v1/hermes/tasks` API, not `/v1/chat/completions`. This keeps long agent runs resilient to HTTP timeouts, client disconnects, and process restarts, while still allowing streaming observation for clients that want live progress.

## Existing Context

`hermes-dingtalk-bridge` already proves the Hermes protocol shape:

- `GET /v1/health`
- `POST /v1/responses`
- bearer token auth
- non-streaming response bodies with `id`, `output`, and/or `output_text`
- streaming SSE events including `response.output_text.delta`, `response.output_item.added`, `response.output_item.done`, `response.completed`, and `response.failed`

`agenthub-openai-gateway` currently exposes OpenAI-compatible `/v1/chat/completions`, model catalog, account/API-key auth, credit ledger, provider visibility control, and usage accounting. That path is optimized for request/response model calls. Hermes agent runs can take much longer and need task state, event replay, and polling.

## Non-Goals

- Do not make Hermes a user custom provider.
- Do not require users to route long Hermes jobs through `/v1/chat/completions`.
- Do not implement distributed workers or a separate queue service in the first version.
- Do not add a new dependency unless the built-in `asyncio` plus SQLite-backed state is insufficient.
- Do not expose arbitrary Hermes admin/control APIs through the gateway.

## Configuration

Add server-side runtime settings:

- `HERMES_ENABLED`: default `false`
- `HERMES_API_BASE`: default `http://127.0.0.1:8642/v1`
- `HERMES_API_KEY`: required when enabled
- `HERMES_MODEL`: default `hermes-agent`
- `HERMES_REQUEST_TIMEOUT_SECONDS`: default `60`
- `HERMES_STREAM_READ_TIMEOUT_SECONDS`: default `1800`
- `HERMES_TASK_MAX_RUNTIME_SECONDS`: default `7200`
- `HERMES_TASK_EVENT_RETENTION_DAYS`: default `30`
- `HERMES_MAX_CONCURRENT_TASKS`: default `2`

The Hermes API key stays only in server config. It is never accepted from customer requests and never returned in API responses.

## API Surface

### Create Task

`POST /v1/hermes/tasks`

Authenticated with the existing gateway bearer API key.

Request:

```json
{
  "input": "帮我分析这个仓库并给出修复方案",
  "conversation": "optional-stable-conversation-id",
  "previous_response_id": "optional-hermes-response-id",
  "instructions": "optional per-task instruction",
  "metadata": {
    "source": "api"
  },
  "stream": false
}
```

Response:

```json
{
  "id": "htask_01HV...",
  "object": "hermes.task",
  "status": "queued",
  "conversation": "acct_123:default",
  "created_at": "2026-04-27T00:00:00Z"
}
```

If `stream=true`, the server may return `text/event-stream` and execute the task while streaming events. The task is still persisted before execution starts, so reconnect and polling work the same way.

### Get Task

`GET /v1/hermes/tasks/{task_id}`

Response:

```json
{
  "id": "htask_01HV...",
  "object": "hermes.task",
  "status": "running",
  "conversation": "acct_123:default",
  "previous_response_id": null,
  "response_id": null,
  "output_text": "partial or final text",
  "error": null,
  "created_at": "2026-04-27T00:00:00Z",
  "started_at": "2026-04-27T00:00:01Z",
  "completed_at": null
}
```

Only the owning account can read its tasks.

### List Tasks

`GET /v1/hermes/tasks?limit=20&offset=0&status=running`

Returns newest-first tasks for the authenticated account. This is useful for API clients that submit async work and later recover local state.

### Stream Task Events

`GET /v1/hermes/tasks/{task_id}/events?after_seq=0`

Returns `text/event-stream`.

Each persisted Hermes event is replayed in order, then the endpoint continues streaming live events until the task reaches a terminal status or the client disconnects.

Example events:

```text
event: task.status
id: 1
data: {"status":"running"}

event: response.output_text.delta
id: 2
data: {"delta":"正在分析..."}

event: response.output_item.added
id: 3
data: {"item":{"type":"function_call","name":"terminal","arguments":"..."}}

event: response.completed
id: 9
data: {"response_id":"resp_123","output_text":"完成。"}
```

The public event names should preserve Hermes event types where possible. Gateway-added lifecycle events use the `task.*` prefix.

### Cancel Task

`POST /v1/hermes/tasks/{task_id}/cancel`

First version marks the task as `cancel_requested`. If Hermes supports request cancellation, the worker forwards cancellation. If not, the gateway stops streaming and marks the task cancelled only after the worker returns or times out.

## Request Mapping To Hermes

The gateway builds a Hermes `/responses` payload:

```json
{
  "model": "hermes-agent",
  "input": "<request.input>",
  "store": true,
  "conversation": "<conversation when no previous_response_id>",
  "previous_response_id": "<previous_response_id when present>",
  "instructions": "<request.instructions or gateway default>",
  "metadata": {
    "gateway_account_id": 123,
    "gateway_api_key_id": 456,
    "gateway_task_id": "htask_...",
    "source": "api"
  },
  "stream": true
}
```

Workers should call Hermes with `stream=true` even for async non-streaming tasks. That lets the gateway persist progress events and partial text. The non-streaming client experience comes from polling `GET /tasks/{id}`.

## Data Model

Add `HermesTaskRecord`:

- `id`: string primary key, public task id
- `account_id`: FK accounts.id, indexed
- `api_key_id`: FK api_keys.id, indexed
- `status`: `queued`, `running`, `completed`, `failed`, `cancel_requested`, `cancelled`, `expired`
- `conversation`: string
- `previous_response_id`: nullable string
- `response_id`: nullable string
- `input_text`: text
- `instructions`: nullable text
- `metadata_json`: text
- `output_text`: text
- `error_code`: nullable string
- `error_message`: nullable text
- `created_at`, `started_at`, `completed_at`, `updated_at`

Add `HermesTaskEventRecord`:

- `id`: integer primary key
- `task_id`: FK hermes_tasks.id, indexed
- `seq`: integer per task
- `event_type`: string
- `payload_json`: text
- `created_at`

Uniqueness:

- `(task_id, seq)` is unique.

Indexes:

- `(account_id, created_at)` for task list.
- `(task_id, seq)` for event replay.
- `(status, created_at)` for worker pickup and cleanup.

## Worker Model

First version runs in-process inside the FastAPI service:

- A startup hook creates a bounded `HermesTaskRunner`.
- The runner owns an `asyncio.Queue` and a semaphore for `HERMES_MAX_CONCURRENT_TASKS`.
- Task creation persists a `queued` row and enqueues its id.
- On startup, the runner requeues stale `queued`, `running`, and `cancel_requested` tasks that are not terminal.
- Each task uses its own DB session and logs lifecycle events.

This avoids introducing Redis/Celery. If later traffic requires horizontal scale, the same DB-backed states can be moved to a distributed worker with row-claiming.

## Streaming And Replay

The worker persists every normalized event before notifying local subscribers.

For `GET /events`:

1. Validate task ownership.
2. Replay stored events with `seq > after_seq`.
3. If task is terminal, emit a final `task.status` event and close.
4. Otherwise subscribe to an in-memory pub/sub channel for live events.
5. On disconnect, leave the task running.

If the API process restarts, live subscriptions disappear but tasks can be resumed from the database and clients can reconnect with `after_seq`.

## Error Handling

Map Hermes and gateway failures to stable task states:

- Hermes 401/403: task `failed`, `error_code=hermes_auth_failed`
- Hermes 404/405/422: task `failed`, `error_code=hermes_request_rejected`
- Hermes network failure: retry with bounded backoff, then `failed`, `error_code=hermes_unavailable`
- Hermes `response.failed`: task `failed`, preserve Hermes error payload
- task runtime exceeds max: `failed`, `error_code=task_timeout`
- client disconnects from `/events`: no task state change

Create-task validation errors still return normal HTTP 4xx. Execution errors should generally be represented in task state instead of turning into a lost HTTP request.

## Billing And Usage

Task creation uses the existing API-key auth and account credit checks.

For first version:

- Quote a conservative minimum execution estimate before enqueueing.
- Do not settle final credit usage until the task reaches `completed` or `failed`.
- If Hermes returns usage metadata, use it.
- If Hermes does not return usage, estimate tokens from `input_text` plus `output_text`, matching existing gateway estimation style.
- Record `provider_name="hermes"` and `model_id="hermes:hermes-agent"` in usage and ledger records.

Failed tasks should record usage with `outcome="error"`. Whether failed tasks charge credits should follow the existing gateway billing policy; if no explicit policy exists, first version should not charge failed tasks unless Hermes returned billable usage.

## Access Control

- Existing bearer API keys authenticate all Hermes task APIs.
- Account status and API-key status/rate limits apply.
- Task reads, event streams, and cancellation are restricted to the owning account.
- Admin model visibility should treat Hermes as a platform service if `HERMES_ENABLED=true`. The model id should be `hermes:hermes-agent`.
- User custom providers remain separate.

## Admin And Portal Surface

First version can be API-only plus model visibility integration.

Recommended follow-up UI:

- Admin Providers/Runtime page: Hermes health, enabled state, base URL, model id, recent task failures.
- Admin Accounts: include `hermes:hermes-agent` in platform model visibility.
- User Portal: API examples for create task, poll task, stream events, cancel task.

## Observability

Emit structured gateway events:

- `gateway.hermes.task.created`
- `gateway.hermes.task.started`
- `gateway.hermes.event.persisted`
- `gateway.hermes.first_delta`
- `gateway.hermes.task.completed`
- `gateway.hermes.task.failed`
- `gateway.hermes.task.cancel_requested`

Logs should include `request_id`, `task_id`, `account_id`, `api_key_id`, `conversation`, and `status`, but never include Hermes API keys.

## Security

- Hermes base URL is configured by the operator, not by users.
- If future admin UI allows editing Hermes URL, reuse provider URL guardrails and block private-network SSRF only when editing remote URLs. Localhost must remain allowed for the server-owned Hermes deployment.
- Redact `input_text` from routine logs; store it in DB because task replay and audit require it.
- Cap metadata size and reject deeply nested or huge metadata payloads.
- Cap input size to a configurable limit.
- Use account ownership checks on every task endpoint.

## Testing Plan

Backend unit/integration tests:

- create task persists `queued` row for authenticated API key
- task worker maps Hermes stream deltas into stored events and final `completed` state
- `GET /tasks/{id}` denies other accounts
- `GET /tasks/{id}/events` replays stored events after `after_seq`
- client event-stream disconnect does not cancel task
- Hermes `response.failed` maps to `failed`
- Hermes network error maps to retry then `failed`
- cancelled task cannot be cancelled twice
- `hermes:hermes-agent` appears in `/v1/models` only when enabled and allowed for account
- usage/ledger rows reference provider `hermes`

Smoke tests:

- local mock Hermes server for non-streaming completion
- local mock Hermes server for SSE completion
- deployed health check confirms gateway stays healthy when Hermes is disabled

## Rollout

1. Ship disabled by default.
2. Deploy code and verify no route behavior changes while `HERMES_ENABLED=false`.
3. Configure server env for Hermes.
4. Enable `hermes:hermes-agent` for one admin/test account.
5. Run create/poll/events/cancel smoke tests.
6. Document API examples in portal docs.

## OpenAI Compatibility Follow-Up

After the dedicated task API is stable, add optional `/v1/chat/completions` support for `model="hermes:hermes-agent"`:

- `stream=true`: proxy Hermes deltas as chat completion chunks.
- `stream=false`: either wait for a bounded synchronous completion or return a clear error instructing clients to use `/v1/hermes/tasks`.
- `background=true`: return a task envelope instead of a chat completion.

This is explicitly a compatibility layer. The long-running, resumable contract remains `/v1/hermes/tasks`.
