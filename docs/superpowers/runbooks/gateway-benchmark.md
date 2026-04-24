# Gateway Benchmark Runbook

Use this script to capture a repeatable local baseline for the gateway.

## Backend Prerequisite

Start the backend first:

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python scripts/run_backend.py
```

## Codex Baseline

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python scripts/benchmark_gateway.py \
  --model codex:gpt-5.4 \
  --iterations 5 \
  --warmup 1
```

## Gemini Baseline

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python scripts/benchmark_gateway.py \
  --model gemini:gemini-2.5-flash \
  --iterations 5 \
  --warmup 1
```

## What To Compare

The script reports:

- `/v1/models` latency
- non-stream completion latency
- stream first-chunk latency
- stream total latency
- optional concurrent non-stream / stream latency buckets for each requested concurrency level

Run the same command before and after runtime changes to compare median and p95.

## Concurrent Sweep

Run a single-model concurrency sweep like this:

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python scripts/benchmark_gateway.py \
  --model codex:gpt-5.4 \
  --iterations 3 \
  --warmup 1 \
  --concurrency-levels 2,4,8 \
  --bootstrap-credits 250
```

The JSON output adds a `concurrency` section keyed by concurrency level. Each level reports:

- `non_stream_ms`
- `stream_first_chunk_ms`
- `stream_total_ms`

## Gemini ACP Soak / Recovery

For the opt-in Gemini ACP path, run a sequential warm-path plus recovery benchmark against a backend instance started with `GEMINI_ACP_ENABLED=true`.

Start a dedicated backend:

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
GEMINI_ACP_ENABLED=true ./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8792
```

Find the backend pid:

```bash
lsof -nP -iTCP:8792 -sTCP:LISTEN
```

Run the soak benchmark:

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python scripts/benchmark_gemini_acp_soak.py \
  --base-url http://127.0.0.1:8792 \
  --model gemini:gemini-2.5-flash \
  --sequential-requests 4 \
  --recovery-cycles 2 \
  --backend-pid <pid> \
  --bootstrap-credits 250
```

The JSON output reports:

- `cold_start_ms`
- `warm_path_ms`
- `recovery_ms`
- `killed_children`

To measure how the single Gemini ACP session behaves when several external callers arrive at once, add a queue-concurrency sweep:

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python scripts/benchmark_gemini_acp_soak.py \
  --base-url http://127.0.0.1:8792 \
  --model gemini:gemini-2.5-flash \
  --sequential-requests 4 \
  --concurrency-levels 2,4,8 \
  --concurrency-rounds 2 \
  --bootstrap-credits 500
```

The JSON output then adds `queue_concurrency`, keyed by concurrency level. Each level reports:

- `request_ms`: latency distribution across all concurrent requests
- `round_wall_ms`: wall-clock duration for each concurrent round
- `requests`: total requests issued for that level
- `rounds`: number of rounds executed

## Current Local Snapshot

Measured on this repo's local runtime on 2026-04-22 with:

- `iterations=3`
- `warmup=1`
- backend at `http://127.0.0.1:8787`

### `codex:gpt-5.4`

- `/v1/models` median: `15.93ms`
- non-stream median: `12127.66ms`
- stream first chunk median: `10806.79ms`
- stream total median: `12791.31ms`

### `gemini:gemini-2.5-flash`

- `/v1/models` median: `15.47ms`
- non-stream median: `12547.60ms`
- stream first chunk median: `12885.77ms`
- stream total median: `12932.09ms`

Treat these as a point-in-time local baseline, not a latency SLO. Re-run the script after runtime changes and compare median plus p95.

## Current Gemini ACP Soak Snapshot

Measured on 2026-04-23 against a local backend started with `GEMINI_ACP_ENABLED=true`, using:

- `sequential_requests=4`
- `recovery_cycles=2`
- child-process kills between recovery probes

### `gemini:gemini-2.5-flash`

- cold start median: `13176.14ms`
- warm path median: `2095.17ms`
- recovery median after forced ACP child death: `13075.66ms`

Interpretation:

- warm session reuse is materially faster than the cold path
- after killing the ACP child, the next request now rebuilds ACP state directly instead of falling back to the legacy Gemini CLI path

## Current Gemini ACP Queue Smoke

Measured on 2026-04-24 against a temporary local backend started with `GEMINI_ACP_ENABLED=true`, using:

- `sequential_requests=2`
- `concurrency-levels=2`
- `concurrency-rounds=1`

### `gemini:gemini-2.5-flash`

- cold start: `11970.20ms`
- warm path: `1601.29ms`
- concurrency `2` request median: `2661.60ms`
- concurrency `2` round wall time: `3635.91ms`

Interpretation:

- the warm ACP path still avoids most cold-start latency
- two concurrent callers are serialized through the single ACP session, so wall time is close to the sum of queued prompt work
- the fuller `2,4,8` sweep below should be used for runtime policy decisions

## Current Gemini ACP Queue Sweep

Measured on 2026-04-24 against a temporary local backend started with `GEMINI_ACP_ENABLED=true`, using:

- `sequential_requests=4`
- `concurrency-levels=2,4,8`
- `concurrency-rounds=2`

### `gemini:gemini-2.5-flash`

- cold start: `12101.56ms`
- warm path median: `1271.18ms`
- warm path p95: `1658.60ms`

| Concurrency | Requests | Request median | Request p95 | Round wall median | Round wall p95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2 | 4 | `5068.37ms` | `10326.14ms` | `6628.31ms` | `10327.38ms` |
| 4 | 8 | `3448.61ms` | `5791.89ms` | `5595.57ms` | `5795.03ms` |
| 8 | 16 | `9997.53ms` | `17173.30ms` | `15317.23ms` | `18524.42ms` |

Interpretation:

- the ACP warm path is fast for single sequential callers
- concurrent callers are still serialized through one ACP session, so tail latency grows with queue depth
- `8` concurrent requests crosses `15s` median wall time locally, so defaulting ACP for broader traffic should wait until stream/cancel behavior and queue policy are explicitly designed

## Current Gemini ACP Stream Smoke

Measured on 2026-04-24 against a temporary local backend started with `GEMINI_ACP_ENABLED=true`, using `benchmark_gateway.py` with `iterations=1` and `warmup=0`.

### `gemini:gemini-2.5-flash`

- non-stream total: `10454.27ms`
- stream first chunk: `1620.31ms`
- stream total: `1636.07ms`

Interpretation:

- the first non-stream call still pays the cold ACP start cost
- the immediately following stream call reuses the warm ACP session and returns the first chunk in under `2s`
- this validates the feature-flagged ACP stream path for a local smoke, but cancellation and longer streaming outputs still need targeted verification
