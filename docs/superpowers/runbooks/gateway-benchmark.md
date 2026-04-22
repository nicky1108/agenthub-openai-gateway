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

Run the same command before and after runtime changes to compare median and p95.

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
