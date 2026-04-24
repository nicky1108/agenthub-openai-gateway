# Gemini ACP And Catalog Hardening Plan

Date: 2026-04-24
Status: In progress
Scope: user-facing latency, model availability, billing trust, and public-gateway reliability

## Goal

Improve the gateway from a feature-complete local control plane into a more reliable external-user service. The work prioritizes the user-visible path: model discovery, request latency, streaming behavior, billing correctness, and reverse-tunnel resilience.

## Decision Drivers

- End-user latency matters more than adding more admin surface area.
- Gateway behavior must stay stable under public-gateway traffic and local CLI provider quirks.
- Billing and pricing must be explainable because credits are user-visible money.
- Provider changes should remain reversible behind feature flags or fallback paths until proven.

## Execution Order

1. [x] Add a Gemini ACP queue-concurrency benchmark.
2. [x] Run a real 2/4/8 Gemini ACP queue benchmark and record the local baseline.
3. [x] Add Gemini ACP stream support behind the existing ACP feature flag.
4. [x] Add conservative Gemini ACP retry and pool controls.
5. [ ] Replace static bootstrap model discovery with provider-backed discovery where available.
6. [ ] Move credit persistence from floating-point storage to an exact representation.
7. [ ] Add reverse-tunnel soak and usage-record end-to-end verification.

## Task 1: Gemini ACP Queue-Concurrency Benchmark

Files:

- Modify: `backend/scripts/benchmark_gemini_acp_soak.py`
- Modify: `backend/tests/test_benchmark_gemini_acp_soak.py`
- Modify: `docs/superpowers/runbooks/gateway-benchmark.md`

Acceptance criteria:

- The benchmark can issue concurrent non-stream Gemini ACP requests against one warm gateway instance.
- The JSON report includes per-request latency and per-round wall-clock latency for each concurrency level.
- The script keeps sequential warm-path and forced-recovery reporting intact.
- Tests cover the report shape without requiring a live Gemini CLI.

## Task 2: Real Queue Baseline

Acceptance criteria:

- Run the queue benchmark with `GEMINI_ACP_ENABLED=true`.
- Capture at least `2,4,8` concurrency levels when the local machine can tolerate it.
- Record median and p95 values in the runbook.
- Identify whether queue wait is dominated by serialized ACP prompts or process/session recovery.

## Task 3: ACP Streaming

Acceptance criteria:

- Gemini stream requests can use ACP updates when `GEMINI_ACP_ENABLED=true`.
- Existing CLI stream remains the fallback.
- Cancellation does not leave a stale ACP prompt in flight.
- Tests cover stream chunks, final usage extraction, fallback, and cancellation.

## Task 4: ACP Retry And Pool Controls

Acceptance criteria:

- Transient ACP failures rebuild ACP state and retry once before falling back to legacy Gemini CLI.
- Stream retry only happens before any SSE chunk is emitted.
- ACP pool size is configurable but defaults to the stable single-session behavior.
- Optional prewarm exists as an explicit tuning switch, not a default, because local benchmark evidence showed multi-process Gemini ACP can degrade warm latency.
- Tests cover retry, warm-slot selection, cold-slot avoidance, and optional prewarm.

## Task 5: Real Model Discovery

Acceptance criteria:

- Static bootstrap remains a fallback, not the only model source.
- Gemini discovery uses a real local provider source when available.
- Codex discovery gets a documented source or a safe probe before changing behavior.
- Admin rediscover clearly labels `provider`, `bootstrap`, `pricing`, and manual entries.

## Task 6: Exact Credit Storage

Acceptance criteria:

- Balances and ledger values avoid float persistence.
- Existing SQLite installs migrate cleanly.
- API responses keep two-decimal user-facing values.
- Regression tests cover small charges, manual adjustments, and insufficient balance.

## Task 7: Reverse Tunnel Soak

Acceptance criteria:

- A runbook command verifies tunnel connect, model catalog, non-stream chat, stream chat, cancel, and usage record.
- Disconnect/reconnect behavior is measurable.
- Usage events are verified through the public-gateway transport path, not only the local internal endpoint.

## Verification

- Focused backend tests for each changed area.
- Real local smoke for Gemini ACP benchmark changes.
- Full affected backend suite before pushing.
- Frontend tests only when UI surfaces change.

## Risks

- Gemini ACP stream event shapes may not map perfectly to OpenAI SSE chunks.
- Static model lists may still be needed for providers that do not expose a reliable catalog.
- Exact credit storage touches account balances and ledger history, so migration tests must be conservative.
