# Gateway Stability And Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the local gateway's reliability, operational safety, billing precision, observability, and end-to-end latency from API ingress to provider execution.

**Architecture:** Keep the existing FastAPI + SQLAlchemy gateway shape, but strengthen five core layers: credit precision, single-instance process safety, request-phase observability, CLI transport efficiency, and database durability/performance defaults. Execute these as small, test-first changes so the gateway remains deployable after each task.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, asyncio, subprocess-based CLI adapters, pytest, pytest-asyncio.

---

## File Map

### Billing Precision

- Modify: `backend/app/core/models.py`
- Modify: `backend/app/billing/service.py`
- Modify: `backend/app/api/admin.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_credits.py`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/i18n.ts`

### Single-Instance Guarding

- Create: `backend/app/runtime/instance_guard.py`
- Create: `backend/scripts/run_backend.py`
- Create: `backend/scripts/run_tunnel_agent.py`
- Modify: `backend/app/tunnel/run_agent.py`
- Modify: `README.md`
- Create: `docs/superpowers/runbooks/local-runtime.md`
- Create: `backend/tests/test_instance_guard.py`

### Observability

- Create: `backend/app/runtime/logging.py`
- Modify: `backend/app/api/openai.py`
- Modify: `backend/app/api/admin.py`
- Modify: `backend/app/orchestration/chat.py`
- Modify: `backend/tests/test_chat_completions_http.py`
- Modify: `backend/tests/test_chat_streaming.py`

### Persistent / Faster CLI Runtime

- Create: `backend/app/runtime/provider_process_pool.py`
- Modify: `backend/app/orchestration/chat.py`
- Modify: `backend/app/adapters/cli/codex.py`
- Modify: `backend/app/adapters/cli/gemini.py`
- Modify: `backend/tests/test_cli_runtime.py`
- Create: `backend/tests/test_provider_process_pool.py`

### Database Durability / Performance

- Modify: `backend/app/core/db.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_sqlite_pragmas.py`

## Working Assumptions

- Current tunnel work is an active adjacent lane. Do not rewrite tunnel contracts as part of this plan.
- Current provider support remains `codex` and `gemini` for real local bring-up. `hermes` / `opencode` stay out of scope.
- SQLite remains the local default for now; phase 1 of this plan improves SQLite behavior rather than replacing it with Postgres.
- Credit precision must move to two decimal places without breaking existing admin flows or ledger semantics.

## Task 1: Upgrade Credits To Two Decimal Places

**Files:**
- Modify: `backend/app/core/models.py`
- Modify: `backend/app/billing/service.py`
- Modify: `backend/app/api/admin.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_credits.py`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write failing billing precision tests**

Add tests that prove:

- manual credit adjustments can store decimal values such as `1500.25`
- ledger entries preserve two decimal places
- successful inference can deduct sub-credit amounts instead of always rounding up to integers
- insufficient-balance logic still blocks requests correctly when decimal balances are involved

- [ ] **Step 2: Run tests to confirm failure**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
./backend/.venv/bin/python -m pytest -q backend/tests/test_credits.py
```

Expected:

- failures around integer-only account balances and ledger values

- [ ] **Step 3: Convert persistence model to fixed-point decimals**

Use precise decimal/fixed-point columns instead of integer credits for:

- `AccountRecord.credit_balance`
- `UsageRecord.credits_charged`
- `CreditLedgerRecord.credits_delta`
- `CreditLedgerRecord.balance_after`

Implement SQLite-safe migration/backfill logic in `backend/app/main.py`.

- [ ] **Step 4: Update billing math**

In `backend/app/billing/service.py`:

- remove integer-only credit math
- round to two decimal places at persistence boundaries
- keep minimum non-zero charge behavior explicit and documented

- [ ] **Step 5: Update admin and frontend serialization**

Ensure admin APIs and frontend render decimal credit balances cleanly.

- [ ] **Step 6: Re-run tests**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
./backend/.venv/bin/python -m pytest -q backend/tests/test_credits.py
```

Expected:

- PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/nicky/agenthub-openai-gateway
git add backend/app/core/models.py backend/app/billing/service.py backend/app/api/admin.py backend/app/main.py backend/tests/test_credits.py frontend/src/api.ts frontend/src/App.tsx frontend/src/i18n.ts
git commit -m "Make gateway credits precise to two decimal places" -m "Constraint: Credit math must stay deterministic under SQLite while preserving existing ledger behavior." -m "Rejected: Keep integer credits | it prevents accurate small-cost settlement and makes ledger values less trustworthy." -m "Confidence: high" -m "Scope-risk: moderate" -m "Directive: Do not reintroduce integer-only credit rounding in billing or admin serialization." -m "Tested: backend/tests/test_credits.py"
```

## Task 2: Enforce Single-Instance Runtime Safety

**Files:**
- Create: `backend/app/runtime/instance_guard.py`
- Create: `backend/scripts/run_backend.py`
- Create: `backend/scripts/run_tunnel_agent.py`
- Modify: `backend/app/tunnel/run_agent.py`
- Create: `backend/tests/test_instance_guard.py`
- Modify: `README.md`
- Create: `docs/superpowers/runbooks/local-runtime.md`

- [ ] **Step 1: Write failing instance-guard tests**

Cover:

- backend detects an existing live instance and refuses duplicate startup
- tunnel agent detects an existing live instance for the same `device_id`
- stale lock/pid files are reclaimed safely

- [ ] **Step 2: Run tests to confirm failure**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
./backend/.venv/bin/python -m pytest -q backend/tests/test_instance_guard.py
```

Expected:

- missing module / missing runtime guard failures

- [ ] **Step 3: Implement process guard**

Create an instance guard using:

- pid file or lock file under a stable runtime directory
- stale-process detection
- per-agent keying for tunnel agent identity

- [ ] **Step 4: Route normal startup through wrapper scripts**

Use:

- `backend/scripts/run_backend.py`
- `backend/scripts/run_tunnel_agent.py`

so operators stop launching raw `uvicorn` / agent commands directly in most cases.

- [ ] **Step 5: Update docs**

Document single-instance startup and cleanup in README + runbook.

- [ ] **Step 6: Re-run tests**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
./backend/.venv/bin/python -m pytest -q backend/tests/test_instance_guard.py
```

Expected:

- PASS

## Task 3: Add Request-Phase Observability

**Files:**
- Create: `backend/app/runtime/logging.py`
- Modify: `backend/app/api/openai.py`
- Modify: `backend/app/api/admin.py`
- Modify: `backend/app/orchestration/chat.py`
- Modify: `backend/tests/test_chat_completions_http.py`
- Modify: `backend/tests/test_chat_streaming.py`

- [ ] **Step 1: Write failing observability tests**

Cover:

- each request gets a stable request id
- logs include provider/model/route_policy/stream flag
- non-stream path records auth/quote/provider/settle timing markers
- stream path records first-chunk latency and total runtime

- [ ] **Step 2: Run tests to confirm failure**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
./backend/.venv/bin/python -m pytest -q backend/tests/test_chat_completions_http.py backend/tests/test_chat_streaming.py
```

Expected:

- failures because structured timing/log context is not yet present

- [ ] **Step 3: Add lightweight structured logging helpers**

Keep this minimal and local:

- request id creation
- monotonic timing helpers
- consistent log event names

- [ ] **Step 4: Instrument `/v1/chat/completions`**

Record at least:

- auth complete
- quote complete
- provider prepare complete
- first chunk emitted
- settle complete
- request finished / failed

- [ ] **Step 5: Re-run tests**

Run the same pytest command.

Expected:

- PASS

## Task 4: Introduce a Persistent CLI Runtime Path

**Files:**
- Create: `backend/app/runtime/provider_process_pool.py`
- Modify: `backend/app/orchestration/chat.py`
- Modify: `backend/app/adapters/cli/codex.py`
- Modify: `backend/app/adapters/cli/gemini.py`
- Modify: `backend/tests/test_cli_runtime.py`
- Create: `backend/tests/test_provider_process_pool.py`

- [ ] **Step 1: Write failing runtime-pool tests**

Cover:

- repeated requests reuse a live runtime/process slot
- stream and non-stream requests still preserve current response shape
- failed/stale workers are evicted and replaced
- cancellation still works

- [ ] **Step 2: Run tests to confirm failure**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
./backend/.venv/bin/python -m pytest -q backend/tests/test_cli_runtime.py backend/tests/test_provider_process_pool.py
```

Expected:

- missing module / no reuse behavior failures

- [ ] **Step 3: Implement a narrow process pool**

Start conservatively:

- one warmed slot per provider/model or provider lane
- bounded idle timeout
- no large generic scheduler

Keep the abstraction small and local to CLI-backed providers.

- [ ] **Step 4: Wire orchestrator to prefer pooled runtime for supported providers**

Limit first rollout to:

- `codex`
- `gemini`

- [ ] **Step 5: Re-run tests**

Expected:

- PASS

## Task 5: Improve SQLite Durability and Write Behavior

**Files:**
- Modify: `backend/app/core/db.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_sqlite_pragmas.py`

- [ ] **Step 1: Write failing SQLite configuration tests**

Cover:

- WAL mode enabled
- sensible busy timeout configured
- foreign keys enabled

- [ ] **Step 2: Run tests to confirm failure**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
./backend/.venv/bin/python -m pytest -q backend/tests/test_sqlite_pragmas.py
```

Expected:

- failures because pragmas are not yet enforced

- [ ] **Step 3: Apply SQLite pragmas at engine/session setup**

Keep scope limited to SQLite only.

- [ ] **Step 4: Re-run tests**

Expected:

- PASS

## Task 6: Final Regression Sweep

**Files:**
- No new code required unless a failure is found

- [ ] **Step 1: Run focused backend verification**

```bash
cd /Users/nicky/agenthub-openai-gateway
./backend/.venv/bin/python -m pytest -q \
  backend/tests/test_credits.py \
  backend/tests/test_cli_runtime.py \
  backend/tests/test_chat_streaming.py \
  backend/tests/test_chat_completions_http.py \
  backend/tests/test_admin_test_chat.py \
  backend/tests/test_internal_public_gateway.py \
  backend/tests/test_tunnel_agent.py \
  backend/tests/test_instance_guard.py \
  backend/tests/test_sqlite_pragmas.py
```

- [ ] **Step 2: Run a manual smoke pass**

Verify:

- backend starts once
- second backend start is rejected cleanly
- agent starts once
- second same-device agent start is rejected cleanly
- `/v1/models`
- non-stream `chat/completions`
- stream `chat/completions`
- admin test chat
- decimal credit adjustment and ledger entry

- [ ] **Step 3: Summarize residual risks**

Document any remaining caveats, especially:

- persistent CLI runtime support boundary
- SQLite concurrency ceiling
- provider-specific runtime behavior differences

## Spec Coverage Check

This plan covers the five requested improvement areas:

- two-decimal credit precision
- single-instance runtime safety
- request-phase observability
- faster CLI execution path via persistent runtime
- SQLite durability/performance defaults

Known intentional omissions:

- `hermes` / `opencode` real bring-up
- Postgres migration
- portal/admin expansion in `agenthub-public-gateway`
