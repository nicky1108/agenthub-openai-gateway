# Hermes Task API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class `/v1/hermes/tasks` API for long-running Hermes agent execution with persisted task state, event replay, streaming observation, cancellation, account isolation, platform model visibility, and billing hooks.

**Architecture:** Keep Hermes separate from the existing OpenAI chat orchestrator. Add a small async Hermes client, a SQLite-backed task/event store, an in-process bounded runner started with FastAPI, and a dedicated authenticated API router. Platform catalog integration exposes `hermes:hermes-agent` only when enabled and account-visible.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, SQLite, httpx async streaming, asyncio queues/semaphores, pytest, FastAPI TestClient.

---

## File Structure

- Create `backend/app/services/hermes_client.py`: async Hermes `/v1/health` and `/v1/responses` client plus SSE event parser.
- Create `backend/app/services/hermes_tasks.py`: task serialization, repository functions, event persistence, account ownership checks, and in-memory event bus.
- Create `backend/app/runtime/hermes_task_runner.py`: bounded in-process task worker that streams Hermes events into persisted task state.
- Create `backend/app/api/hermes.py`: authenticated task routes under `/v1/hermes`.
- Create `backend/tests/test_hermes_client.py`: client parser and HTTP behavior tests.
- Create `backend/tests/test_hermes_tasks.py`: DB state, event replay, and account ownership tests.
- Create `backend/tests/test_hermes_api.py`: API contract tests for create/get/list/events/cancel.
- Modify `backend/app/core/settings.py`: Hermes settings.
- Modify `backend/app/core/models.py`: `HermesTaskRecord` and `HermesTaskEventRecord`.
- Modify `backend/app/main.py`: table creation already covers new tables; include Hermes router; start/stop runner.
- Modify `backend/app/registry/service.py` or add a focused catalog helper: include the virtual Hermes platform model when enabled.
- Modify `backend/app/api/admin.py`, `backend/app/api/openai.py`, and `backend/app/api/portal.py`: use the unified platform model list so account visibility includes Hermes.
- Modify `README.md`: add concise Hermes task API examples.

Keep the first implementation API-only. Do not add admin/portal UI in this plan.

---

### Task 1: Settings And Schema

**Files:**
- Modify: `backend/app/core/settings.py`
- Modify: `backend/app/core/models.py`
- Test: `backend/tests/test_hermes_tasks.py`

- [ ] **Step 1: Write failing schema/settings tests**

Create `backend/tests/test_hermes_tasks.py` with:

```python
from sqlalchemy import text

from app.core.db import create_engine_and_sessionmaker
from app.core.models import Base
from app.core.settings import Settings


def test_hermes_settings_read_environment(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.setenv("HERMES_API_BASE", "http://127.0.0.1:8642/v1")
    monkeypatch.setenv("HERMES_API_KEY", "secret")
    monkeypatch.setenv("HERMES_MODEL", "hermes-agent")
    monkeypatch.setenv("HERMES_MAX_CONCURRENT_TASKS", "3")

    settings = Settings()

    assert settings.hermes_enabled is True
    assert settings.hermes_api_base == "http://127.0.0.1:8642/v1"
    assert settings.hermes_api_key == "secret"
    assert settings.hermes_model == "hermes-agent"
    assert settings.hermes_max_concurrent_tasks == 3


async def test_hermes_tables_are_created(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    engine, _ = create_engine_and_sessionmaker()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        tables = {
            row[0]
            for row in (
                await connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                )
            ).all()
        }
        task_columns = {
            row[1]
            for row in (
                await connection.execute(text("PRAGMA table_info(hermes_tasks)"))
            ).all()
        }
        event_columns = {
            row[1]
            for row in (
                await connection.execute(text("PRAGMA table_info(hermes_task_events)"))
            ).all()
        }

    await engine.dispose()

    assert "hermes_tasks" in tables
    assert "hermes_task_events" in tables
    assert {"id", "account_id", "api_key_id", "status", "input_text", "output_text"} <= task_columns
    assert {"task_id", "seq", "event_type", "payload_json"} <= event_columns
```

- [ ] **Step 2: Run the new tests and verify failure**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q tests/test_hermes_tasks.py
```

Expected: fails because `Settings` has no Hermes fields and the tables do not exist.

- [ ] **Step 3: Add Hermes settings**

In `backend/app/core/settings.py`, add these fields to `Settings` near the existing provider runtime settings:

```python
    hermes_enabled: bool = False
    hermes_api_base: str = "http://127.0.0.1:8642/v1"
    hermes_api_key: str | None = None
    hermes_model: str = "hermes-agent"
    hermes_request_timeout_seconds: float = 60.0
    hermes_stream_read_timeout_seconds: float = 1800.0
    hermes_task_max_runtime_seconds: float = 7200.0
    hermes_task_event_retention_days: int = 30
    hermes_max_concurrent_tasks: int = 2
    hermes_input_max_chars: int = 200_000
    hermes_metadata_max_bytes: int = 16_384
```

Update `validate_secure_runtime_config`:

```python
    if settings.hermes_enabled and not settings.hermes_api_key:
        raise RuntimeError("HERMES_API_KEY must be configured when HERMES_ENABLED=true")
```

- [ ] **Step 4: Add Hermes task models**

In `backend/app/core/models.py`, add the new classes after `CreditLedgerRecord` or near related usage records:

```python
class HermesTaskRecord(Base):
    __tablename__ = "hermes_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="queued")
    conversation: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    previous_response_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    response_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class HermesTaskEventRecord(Base):
    __tablename__ = "hermes_task_events"
    __table_args__ = (UniqueConstraint("task_id", "seq", name="uq_hermes_task_events_seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("hermes_tasks.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
```

- [ ] **Step 5: Run schema/settings tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q tests/test_hermes_tasks.py
```

Expected: both tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/settings.py backend/app/core/models.py backend/tests/test_hermes_tasks.py
git commit -m "Add Hermes task settings and schema"
```

---

### Task 2: Hermes Client And Event Parser

**Files:**
- Create: `backend/app/services/hermes_client.py`
- Test: `backend/tests/test_hermes_client.py`

- [ ] **Step 1: Write failing client tests**

Create `backend/tests/test_hermes_client.py`:

```python
import json

import httpx
import pytest

from app.services.hermes_client import (
    HermesClient,
    HermesRequest,
    HermesResponseEvent,
    extract_hermes_output_text,
)


@pytest.mark.asyncio
async def test_hermes_client_streams_text_and_completion() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        assert request.headers["authorization"] == "Bearer test-key"
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "hermes-agent"
        assert body["input"] == "run task"
        assert body["stream"] is True
        stream = "\n\n".join(
            [
                'data: {"type":"response.output_text.delta","delta":"hello"}',
                'data: {"type":"response.output_text.delta","delta":" world"}',
                'data: {"type":"response.completed","response":{"id":"resp-1","output_text":"hello world"}}',
                "data: [DONE]",
            ]
        )
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=stream)

    client = HermesClient(
        base_url="http://hermes.local/v1",
        api_key="test-key",
        model="hermes-agent",
        transport=httpx.MockTransport(handler),
    )

    events = [
        event
        async for event in client.stream_response(
            HermesRequest(input_text="run task", conversation="acct:default", metadata={"source": "test"})
        )
    ]

    assert [event.type for event in events] == [
        "response.output_text.delta",
        "response.output_text.delta",
        "response.completed",
    ]
    assert events[0].payload == {"delta": "hello"}
    assert events[-1].payload["response"]["id"] == "resp-1"


def test_extract_hermes_output_text_supports_output_array() -> None:
    payload = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "first"},
                    {"type": "text", "text": "second"},
                ],
            }
        ]
    }

    assert extract_hermes_output_text(payload) == "first\nsecond"


def test_hermes_response_event_rejects_empty_type() -> None:
    with pytest.raises(ValueError, match="event type is required"):
        HermesResponseEvent(type="", payload={})
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q tests/test_hermes_client.py
```

Expected: import failure for `app.services.hermes_client`.

- [ ] **Step 3: Implement Hermes client**

Create `backend/app/services/hermes_client.py`:

```python
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx


class HermesApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class HermesRequest:
    input_text: str
    conversation: str
    previous_response_id: str | None = None
    instructions: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HermesResponseEvent:
    type: str
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.type:
            raise ValueError("event type is required")


def extract_hermes_output_text(response: dict[str, Any]) -> str:
    output = response.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                        text = content.get("text")
                        if text:
                            chunks.append(str(text))
            elif item.get("type") == "output_text":
                text = item.get("text")
                if text:
                    chunks.append(str(text))
        if chunks:
            return "\n".join(chunks).strip()
    if isinstance(response.get("output_text"), str):
        return str(response["output_text"]).strip()
    return ""


class HermesClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        request_timeout_seconds: float = 60.0,
        stream_read_timeout_seconds: float = 1800.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.request_timeout_seconds = request_timeout_seconds
        self.stream_read_timeout_seconds = stream_read_timeout_seconds
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _payload(self, request: HermesRequest, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": request.input_text,
            "store": True,
            "stream": stream,
        }
        if request.previous_response_id:
            payload["previous_response_id"] = request.previous_response_id
        else:
            payload["conversation"] = request.conversation
        if request.instructions:
            payload["instructions"] = request.instructions
        if request.metadata:
            payload["metadata"] = request.metadata
        return payload

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self.request_timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.get(f"{self.base_url}/health", headers=self._headers())
        if response.status_code >= 400:
            raise HermesApiError(response.text, status_code=response.status_code)
        parsed = response.json() if response.content else {}
        return parsed if isinstance(parsed, dict) else {}

    async def create_response(self, request: HermesRequest) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self.request_timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.post(
                f"{self.base_url}/responses",
                headers=self._headers(),
                json=self._payload(request, stream=False),
            )
        if response.status_code >= 400:
            raise HermesApiError(response.text, status_code=response.status_code)
        parsed = response.json() if response.content else {}
        if not isinstance(parsed, dict):
            raise HermesApiError("Unexpected Hermes API response shape")
        return parsed

    async def stream_response(self, request: HermesRequest) -> AsyncIterator[HermesResponseEvent]:
        timeout = httpx.Timeout(
            connect=self.request_timeout_seconds,
            read=self.stream_read_timeout_seconds,
            write=self.request_timeout_seconds,
            pool=self.request_timeout_seconds,
        )
        async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/responses",
                headers=self._headers(),
                json=self._payload(request, stream=True),
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise HermesApiError(body.decode("utf-8", errors="replace"), status_code=response.status_code)
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    raw = await response.aread()
                    parsed = json.loads(raw.decode("utf-8")) if raw else {}
                    if isinstance(parsed, dict):
                        yield HermesResponseEvent(
                            type="response.completed",
                            payload={"response": parsed},
                        )
                    return
                async for raw_line in response.aiter_lines():
                    line = (raw_line or "").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    event = json.loads(data)
                    if not isinstance(event, dict):
                        continue
                    event_type = str(event.get("type") or "")
                    if event_type == "response.output_text.delta":
                        yield HermesResponseEvent(type=event_type, payload={"delta": str(event.get("delta") or "")})
                        continue
                    yield HermesResponseEvent(type=event_type, payload=event)
```

- [ ] **Step 4: Run client tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q tests/test_hermes_client.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/hermes_client.py backend/tests/test_hermes_client.py
git commit -m "Add Hermes API client"
```

---

### Task 3: Task Store, Serialization, And Event Bus

**Files:**
- Create: `backend/app/services/hermes_tasks.py`
- Modify: `backend/tests/test_hermes_tasks.py`

- [ ] **Step 1: Add failing repository tests**

Append to `backend/tests/test_hermes_tasks.py`:

```python
import pytest

from app.core.models import AccountRecord, ApiKeyRecord
from app.services.hermes_tasks import (
    HERMES_STATUS_COMPLETED,
    HERMES_STATUS_QUEUED,
    HermesTaskCreate,
    append_hermes_task_event,
    create_hermes_task,
    get_hermes_task_for_account,
    list_hermes_task_events,
    list_hermes_tasks_for_account,
)


@pytest.mark.asyncio
async def test_create_task_and_replay_events(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    engine, sessionmaker = create_engine_and_sessionmaker()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessionmaker() as session:
        account = AccountRecord(name="acct", credit_balance=100)
        session.add(account)
        await session.flush()
        api_key = ApiKeyRecord(account_id=account.id, name="key", key_prefix="sk-test", secret_hash="hash")
        session.add(api_key)
        await session.commit()

        task = await create_hermes_task(
            session,
            account=account,
            api_key=api_key,
            payload=HermesTaskCreate(input_text="hello", metadata={"source": "test"}),
        )
        await append_hermes_task_event(
            session,
            task_id=task.id,
            event_type="response.output_text.delta",
            payload={"delta": "hi"},
        )
        await session.commit()

        loaded = await get_hermes_task_for_account(session, task.id, account.id)
        events = await list_hermes_task_events(session, task.id, after_seq=0)
        page = await list_hermes_tasks_for_account(session, account.id, limit=10, offset=0, status=None)

    await engine.dispose()

    assert loaded is not None
    assert loaded.status == HERMES_STATUS_QUEUED
    assert loaded.conversation == f"acct:{account.id}:default"
    assert events[0].seq == 1
    assert events[0].event_type == "response.output_text.delta"
    assert page["total"] == 1
    assert page["items"][0].id == task.id
```

- [ ] **Step 2: Run repository test and verify failure**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q tests/test_hermes_tasks.py::test_create_task_and_replay_events
```

Expected: import failure for `app.services.hermes_tasks`.

- [ ] **Step 3: Implement task service**

Create `backend/app/services/hermes_tasks.py`:

```python
from __future__ import annotations

import asyncio
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import AccountRecord, ApiKeyRecord, HermesTaskEventRecord, HermesTaskRecord

HERMES_STATUS_QUEUED = "queued"
HERMES_STATUS_RUNNING = "running"
HERMES_STATUS_COMPLETED = "completed"
HERMES_STATUS_FAILED = "failed"
HERMES_STATUS_CANCEL_REQUESTED = "cancel_requested"
HERMES_STATUS_CANCELLED = "cancelled"
HERMES_STATUS_EXPIRED = "expired"
HERMES_TERMINAL_STATUSES = {
    HERMES_STATUS_COMPLETED,
    HERMES_STATUS_FAILED,
    HERMES_STATUS_CANCELLED,
    HERMES_STATUS_EXPIRED,
}


@dataclass(frozen=True, slots=True)
class HermesTaskCreate:
    input_text: str
    conversation: str | None = None
    previous_response_id: str | None = None
    instructions: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HermesTaskEventBusMessage:
    task_id: str
    seq: int
    event_type: str
    payload: dict[str, Any]


class HermesTaskEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[HermesTaskEventBusMessage]]] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue[HermesTaskEventBusMessage]:
        queue: asyncio.Queue[HermesTaskEventBusMessage] = asyncio.Queue()
        self._subscribers.setdefault(task_id, set()).add(queue)
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue[HermesTaskEventBusMessage]) -> None:
        subscribers = self._subscribers.get(task_id)
        if not subscribers:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(task_id, None)

    async def publish(self, message: HermesTaskEventBusMessage) -> None:
        for queue in list(self._subscribers.get(message.task_id, set())):
            await queue.put(message)


hermes_task_event_bus = HermesTaskEventBus()


def new_hermes_task_id() -> str:
    return "htask_" + secrets.token_urlsafe(18).replace("-", "").replace("_", "")[:24]


def default_conversation(account_id: int) -> str:
    return f"acct:{account_id}:default"


async def create_hermes_task(
    session: AsyncSession,
    *,
    account: AccountRecord,
    api_key: ApiKeyRecord,
    payload: HermesTaskCreate,
) -> HermesTaskRecord:
    now = datetime.now(timezone.utc)
    task = HermesTaskRecord(
        id=new_hermes_task_id(),
        account_id=account.id,
        api_key_id=api_key.id,
        status=HERMES_STATUS_QUEUED,
        conversation=payload.conversation or default_conversation(account.id),
        previous_response_id=payload.previous_response_id,
        input_text=payload.input_text,
        instructions=payload.instructions,
        metadata_json=json.dumps(payload.metadata, ensure_ascii=False, separators=(",", ":")),
        output_text="",
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    await session.flush()
    return task


async def get_hermes_task_for_account(
    session: AsyncSession,
    task_id: str,
    account_id: int,
) -> HermesTaskRecord | None:
    return await session.scalar(
        select(HermesTaskRecord).where(
            HermesTaskRecord.id == task_id,
            HermesTaskRecord.account_id == account_id,
        )
    )


async def list_hermes_tasks_for_account(
    session: AsyncSession,
    account_id: int,
    *,
    limit: int,
    offset: int,
    status: str | None,
) -> dict[str, Any]:
    filters = [HermesTaskRecord.account_id == account_id]
    if status:
        filters.append(HermesTaskRecord.status == status)
    total = await session.scalar(select(func.count()).select_from(HermesTaskRecord).where(*filters))
    rows = list(
        await session.scalars(
            select(HermesTaskRecord)
            .where(*filters)
            .order_by(HermesTaskRecord.created_at.desc(), HermesTaskRecord.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return {"items": rows, "total": int(total or 0), "limit": limit, "offset": offset}


async def append_hermes_task_event(
    session: AsyncSession,
    *,
    task_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> HermesTaskEventRecord:
    current_max = await session.scalar(
        select(func.max(HermesTaskEventRecord.seq)).where(HermesTaskEventRecord.task_id == task_id)
    )
    row = HermesTaskEventRecord(
        task_id=task_id,
        seq=int(current_max or 0) + 1,
        event_type=event_type,
        payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )
    session.add(row)
    await session.flush()
    await hermes_task_event_bus.publish(
        HermesTaskEventBusMessage(task_id=task_id, seq=row.seq, event_type=event_type, payload=payload)
    )
    return row


async def list_hermes_task_events(
    session: AsyncSession,
    task_id: str,
    *,
    after_seq: int,
) -> list[HermesTaskEventRecord]:
    return list(
        await session.scalars(
            select(HermesTaskEventRecord)
            .where(
                HermesTaskEventRecord.task_id == task_id,
                HermesTaskEventRecord.seq > after_seq,
            )
            .order_by(HermesTaskEventRecord.seq.asc())
        )
    )
```

- [ ] **Step 4: Run task tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q tests/test_hermes_tasks.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/hermes_tasks.py backend/tests/test_hermes_tasks.py
git commit -m "Add Hermes task store"
```

---

### Task 4: In-Process Hermes Task Runner

**Files:**
- Create: `backend/app/runtime/hermes_task_runner.py`
- Create: `backend/tests/test_hermes_task_runner.py`

- [ ] **Step 1: Write failing runner test**

Create `backend/tests/test_hermes_task_runner.py`:

```python
import pytest

from app.core.db import create_engine_and_sessionmaker
from app.core.models import AccountRecord, ApiKeyRecord, Base
from app.services.hermes_client import HermesResponseEvent
from app.services.hermes_tasks import (
    HERMES_STATUS_COMPLETED,
    HermesTaskCreate,
    create_hermes_task,
    get_hermes_task_for_account,
    list_hermes_task_events,
)
from app.runtime.hermes_task_runner import HermesTaskRunner


class FakeHermesClient:
    async def stream_response(self, request):
        yield HermesResponseEvent(type="response.output_text.delta", payload={"delta": "hello"})
        yield HermesResponseEvent(type="response.output_text.delta", payload={"delta": " world"})
        yield HermesResponseEvent(
            type="response.completed",
            payload={"response": {"id": "resp-1", "output_text": "hello world"}},
        )


@pytest.mark.asyncio
async def test_runner_completes_task_and_persists_events(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    engine, sessionmaker = create_engine_and_sessionmaker()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessionmaker() as session:
        account = AccountRecord(name="acct", credit_balance=100)
        session.add(account)
        await session.flush()
        api_key = ApiKeyRecord(account_id=account.id, name="key", key_prefix="sk-test", secret_hash="hash")
        session.add(api_key)
        await session.commit()
        task = await create_hermes_task(
            session,
            account=account,
            api_key=api_key,
            payload=HermesTaskCreate(input_text="hello"),
        )
        await session.commit()

    runner = HermesTaskRunner(
        sessionmaker=sessionmaker,
        client_factory=lambda: FakeHermesClient(),
        max_concurrent_tasks=1,
        task_max_runtime_seconds=60,
    )
    await runner.run_task_once(task.id)

    async with sessionmaker() as session:
        loaded = await get_hermes_task_for_account(session, task.id, account.id)
        events = await list_hermes_task_events(session, task.id, after_seq=0)

    await engine.dispose()

    assert loaded is not None
    assert loaded.status == HERMES_STATUS_COMPLETED
    assert loaded.output_text == "hello world"
    assert loaded.response_id == "resp-1"
    assert [event.event_type for event in events] == [
        "task.status",
        "response.output_text.delta",
        "response.output_text.delta",
        "response.completed",
        "task.status",
    ]
```

- [ ] **Step 2: Run runner test and verify failure**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q tests/test_hermes_task_runner.py
```

Expected: import failure for `app.runtime.hermes_task_runner`.

- [ ] **Step 3: Implement runner**

Create `backend/app/runtime/hermes_task_runner.py`:

```python
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.models import HermesTaskRecord
from app.core.settings import Settings
from app.runtime.logging import log_gateway_event
from app.services.hermes_client import HermesApiError, HermesClient, HermesRequest, extract_hermes_output_text
from app.services.hermes_tasks import (
    HERMES_STATUS_CANCEL_REQUESTED,
    HERMES_STATUS_CANCELLED,
    HERMES_STATUS_COMPLETED,
    HERMES_STATUS_FAILED,
    HERMES_STATUS_QUEUED,
    HERMES_STATUS_RUNNING,
    append_hermes_task_event,
)


def build_hermes_client(settings: Settings | None = None) -> HermesClient:
    settings = settings or Settings()
    return HermesClient(
        base_url=settings.hermes_api_base,
        api_key=settings.hermes_api_key or "",
        model=settings.hermes_model,
        request_timeout_seconds=settings.hermes_request_timeout_seconds,
        stream_read_timeout_seconds=settings.hermes_stream_read_timeout_seconds,
    )


class HermesTaskRunner:
    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker,
        client_factory: Callable[[], Any] = build_hermes_client,
        max_concurrent_tasks: int = 2,
        task_max_runtime_seconds: float = 7200.0,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.client_factory = client_factory
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.semaphore = asyncio.Semaphore(max(1, max_concurrent_tasks))
        self.task_max_runtime_seconds = task_max_runtime_seconds
        self._workers: list[asyncio.Task[None]] = []
        self._stopped = asyncio.Event()

    async def enqueue(self, task_id: str) -> None:
        await self.queue.put(task_id)

    async def start(self, worker_count: int | None = None) -> None:
        count = worker_count or max(1, self.semaphore._value)
        self._stopped.clear()
        for _ in range(count):
            self._workers.append(asyncio.create_task(self._worker()))

    async def stop(self) -> None:
        self._stopped.set()
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def _worker(self) -> None:
        while not self._stopped.is_set():
            task_id = await self.queue.get()
            try:
                async with self.semaphore:
                    await self.run_task_once(task_id)
            finally:
                self.queue.task_done()

    async def requeue_open_tasks(self) -> None:
        async with self.sessionmaker() as session:
            rows = list(
                await session.scalars(
                    select(HermesTaskRecord)
                    .where(HermesTaskRecord.status.in_([HERMES_STATUS_QUEUED, HERMES_STATUS_RUNNING, HERMES_STATUS_CANCEL_REQUESTED]))
                    .order_by(HermesTaskRecord.created_at.asc())
                )
            )
        for row in rows:
            await self.enqueue(row.id)

    async def run_task_once(self, task_id: str) -> None:
        started_at = datetime.now(timezone.utc)
        output_chunks: list[str] = []
        response_id: str | None = None
        async with self.sessionmaker() as session:
            task = await session.get(HermesTaskRecord, task_id)
            if task is None:
                return
            if task.status == HERMES_STATUS_CANCEL_REQUESTED:
                task.status = HERMES_STATUS_CANCELLED
                task.completed_at = started_at
                task.updated_at = started_at
                await append_hermes_task_event(session, task_id=task.id, event_type="task.status", payload={"status": task.status})
                await session.commit()
                return
            task.status = HERMES_STATUS_RUNNING
            task.started_at = task.started_at or started_at
            task.updated_at = started_at
            await append_hermes_task_event(session, task_id=task.id, event_type="task.status", payload={"status": task.status})
            await session.commit()

            request = HermesRequest(
                input_text=task.input_text,
                conversation=task.conversation,
                previous_response_id=task.previous_response_id,
                instructions=task.instructions,
                metadata=json.loads(task.metadata_json or "{}"),
            )

        try:
            async with asyncio.timeout(self.task_max_runtime_seconds):
                async for event in self.client_factory().stream_response(request):
                    async with self.sessionmaker() as session:
                        task = await session.get(HermesTaskRecord, task_id)
                        if task is None:
                            return
                        if task.status == HERMES_STATUS_CANCEL_REQUESTED:
                            task.status = HERMES_STATUS_CANCELLED
                            task.completed_at = datetime.now(timezone.utc)
                            task.updated_at = task.completed_at
                            await append_hermes_task_event(session, task_id=task.id, event_type="task.status", payload={"status": task.status})
                            await session.commit()
                            return
                        if event.type == "response.output_text.delta":
                            delta = str(event.payload.get("delta") or "")
                            output_chunks.append(delta)
                            task.output_text = "".join(output_chunks)
                        if event.type == "response.completed":
                            response = event.payload.get("response")
                            if isinstance(response, dict):
                                response_id = response.get("id")
                                final_text = extract_hermes_output_text(response)
                                if final_text:
                                    task.output_text = final_text
                        await append_hermes_task_event(
                            session,
                            task_id=task.id,
                            event_type=event.type,
                            payload=event.payload,
                        )
                        task.updated_at = datetime.now(timezone.utc)
                        await session.commit()
        except TimeoutError:
            await self._mark_failed(task_id, "task_timeout", "Hermes task exceeded max runtime")
            return
        except HermesApiError as exc:
            await self._mark_failed(task_id, "hermes_request_failed", str(exc))
            return
        except Exception as exc:
            await self._mark_failed(task_id, "task_failed", str(exc))
            return

        async with self.sessionmaker() as session:
            task = await session.get(HermesTaskRecord, task_id)
            if task is None:
                return
            task.status = HERMES_STATUS_COMPLETED
            task.response_id = response_id
            task.completed_at = datetime.now(timezone.utc)
            task.updated_at = task.completed_at
            if not task.output_text:
                task.output_text = "".join(output_chunks)
            await append_hermes_task_event(session, task_id=task.id, event_type="task.status", payload={"status": task.status})
            await session.commit()
            log_gateway_event("gateway.hermes.task.completed", task_id=task.id, account_id=task.account_id)

    async def _mark_failed(self, task_id: str, error_code: str, error_message: str) -> None:
        async with self.sessionmaker() as session:
            task = await session.get(HermesTaskRecord, task_id)
            if task is None:
                return
            task.status = HERMES_STATUS_FAILED
            task.error_code = error_code
            task.error_message = error_message
            task.completed_at = datetime.now(timezone.utc)
            task.updated_at = task.completed_at
            await append_hermes_task_event(
                session,
                task_id=task.id,
                event_type="task.status",
                payload={"status": task.status, "error_code": error_code, "error_message": error_message},
            )
            await session.commit()
            log_gateway_event("gateway.hermes.task.failed", task_id=task.id, account_id=task.account_id, error_code=error_code)
```

- [ ] **Step 4: Run runner test**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q tests/test_hermes_task_runner.py
```

Expected: test passes.

- [ ] **Step 5: Commit**

```bash
git add backend/app/runtime/hermes_task_runner.py backend/tests/test_hermes_task_runner.py
git commit -m "Add Hermes task runner"
```

---

### Task 5: Hermes Task API Routes

**Files:**
- Create: `backend/app/api/hermes.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_hermes_api.py`

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/test_hermes_api.py`:

```python
import json

from fastapi.testclient import TestClient

from app.main import create_app


def _create_account_and_key(client: TestClient) -> str:
    account_response = client.post(
        "/admin/accounts",
        json={"name": "hermes-account"},
        headers={"x-admin-secret": "change-me"},
    )
    assert account_response.status_code == 201
    key_response = client.post(
        "/admin/api-keys",
        json={"account_id": account_response.json()["id"], "name": "hermes-key"},
        headers={"x-admin-secret": "change-me"},
    )
    assert key_response.status_code == 201
    return key_response.json()["api_key"]


def test_create_and_get_hermes_task(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.setenv("HERMES_API_KEY", "test-hermes-key")

    with TestClient(create_app()) as client:
        api_key = _create_account_and_key(client)
        create_response = client.post(
            "/v1/hermes/tasks",
            json={"input": "run long job", "metadata": {"source": "test"}},
            headers={"authorization": f"Bearer {api_key}"},
        )
        task_id = create_response.json()["id"]
        get_response = client.get(
            f"/v1/hermes/tasks/{task_id}",
            headers={"authorization": f"Bearer {api_key}"},
        )
        list_response = client.get(
            "/v1/hermes/tasks",
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert create_response.status_code == 202
    assert create_response.json()["status"] == "queued"
    assert get_response.status_code == 200
    assert get_response.json()["id"] == task_id
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1


def test_hermes_task_api_requires_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("HERMES_ENABLED", "false")

    with TestClient(create_app()) as client:
        api_key = _create_account_and_key(client)
        response = client.post(
            "/v1/hermes/tasks",
            json={"input": "run long job"},
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Hermes task API is disabled"}
```

- [ ] **Step 2: Run API tests and verify failure**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q tests/test_hermes_api.py
```

Expected: 404 for missing route or import failure.

- [ ] **Step 3: Implement API router**

Create `backend/app/api/hermes.py`:

```python
from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthContext, require_api_key
from app.core.db import get_session
from app.core.models import HermesTaskEventRecord, HermesTaskRecord
from app.core.settings import Settings
from app.services.hermes_tasks import (
    HERMES_STATUS_CANCEL_REQUESTED,
    HERMES_TERMINAL_STATUSES,
    HermesTaskCreate,
    append_hermes_task_event,
    create_hermes_task,
    get_hermes_task_for_account,
    hermes_task_event_bus,
    list_hermes_task_events,
    list_hermes_tasks_for_account,
)

router = APIRouter(prefix="/v1/hermes", tags=["hermes"])


def get_settings() -> Settings:
    return Settings()


def require_hermes_enabled(settings: Settings = Depends(get_settings)) -> Settings:
    if not settings.hermes_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hermes task API is disabled")
    if not settings.hermes_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Hermes API key is not configured")
    return settings


def get_hermes_runner(request: Request):
    return getattr(request.app.state, "hermes_task_runner", None)


class HermesTaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str
    conversation: str | None = None
    previous_response_id: str | None = None
    instructions: str | None = None
    metadata: dict[str, Any] = {}
    stream: bool = False

    @field_validator("input")
    @classmethod
    def validate_input(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("input is required")
        return value


class HermesTaskRead(BaseModel):
    id: str
    object: Literal["hermes.task"] = "hermes.task"
    status: str
    conversation: str
    previous_response_id: str | None
    response_id: str | None
    output_text: str
    error: dict[str, str | None] | None
    created_at: str
    started_at: str | None
    completed_at: str | None


class HermesTaskPage(BaseModel):
    object: Literal["list"] = "list"
    items: list[HermesTaskRead]
    total: int
    limit: int
    offset: int


def serialize_task(task: HermesTaskRecord) -> HermesTaskRead:
    return HermesTaskRead(
        id=task.id,
        status=task.status,
        conversation=task.conversation,
        previous_response_id=task.previous_response_id,
        response_id=task.response_id,
        output_text=task.output_text,
        error=(
            {"code": task.error_code, "message": task.error_message}
            if task.error_code or task.error_message
            else None
        ),
        created_at=task.created_at.isoformat(),
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )


def sse_event(event_type: str, seq: int, payload: dict[str, Any]) -> str:
    return f"event: {event_type}\nid: {seq}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/tasks", response_model=HermesTaskRead, status_code=status.HTTP_202_ACCEPTED)
async def create_task(
    payload: HermesTaskCreateRequest,
    _: Settings = Depends(require_hermes_enabled),
    runner=Depends(get_hermes_runner),
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_key),
) -> HermesTaskRead:
    task = await create_hermes_task(
        session,
        account=auth.account,
        api_key=auth.api_key,
        payload=HermesTaskCreate(
            input_text=payload.input,
            conversation=payload.conversation,
            previous_response_id=payload.previous_response_id,
            instructions=payload.instructions,
            metadata=payload.metadata,
        ),
    )
    await session.commit()
    if runner is not None:
        await runner.enqueue(task.id)
    return serialize_task(task)


@router.get("/tasks", response_model=HermesTaskPage)
async def list_tasks(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: Settings = Depends(require_hermes_enabled),
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_key),
) -> HermesTaskPage:
    page = await list_hermes_tasks_for_account(
        session,
        auth.account.id,
        limit=limit,
        offset=offset,
        status=status_filter,
    )
    return HermesTaskPage(
        items=[serialize_task(task) for task in page["items"]],
        total=page["total"],
        limit=page["limit"],
        offset=page["offset"],
    )


@router.get("/tasks/{task_id}", response_model=HermesTaskRead)
async def get_task(
    task_id: str,
    _: Settings = Depends(require_hermes_enabled),
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_key),
) -> HermesTaskRead:
    task = await get_hermes_task_for_account(session, task_id, auth.account.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hermes task not found")
    return serialize_task(task)


@router.post("/tasks/{task_id}/cancel", response_model=HermesTaskRead)
async def cancel_task(
    task_id: str,
    _: Settings = Depends(require_hermes_enabled),
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_key),
) -> HermesTaskRead:
    task = await get_hermes_task_for_account(session, task_id, auth.account.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hermes task not found")
    if task.status not in HERMES_TERMINAL_STATUSES:
        task.status = HERMES_STATUS_CANCEL_REQUESTED
        await append_hermes_task_event(
            session,
            task_id=task.id,
            event_type="task.status",
            payload={"status": task.status},
        )
        await session.commit()
        await session.refresh(task)
    return serialize_task(task)


@router.get("/tasks/{task_id}/events")
async def stream_task_events(
    task_id: str,
    after_seq: int = Query(default=0, ge=0),
    _: Settings = Depends(require_hermes_enabled),
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_key),
) -> StreamingResponse:
    task = await get_hermes_task_for_account(session, task_id, auth.account.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hermes task not found")

    async def event_stream():
        current_after_seq = after_seq
        stored_events = await list_hermes_task_events(session, task_id, after_seq=current_after_seq)
        for event in stored_events:
            current_after_seq = event.seq
            yield sse_event(event.event_type, event.seq, json.loads(event.payload_json))
        if task.status in HERMES_TERMINAL_STATUSES:
            return
        queue = hermes_task_event_bus.subscribe(task_id)
        try:
            while True:
                message = await queue.get()
                if message.seq <= current_after_seq:
                    continue
                yield sse_event(message.event_type, message.seq, message.payload)
                if message.event_type == "task.status" and message.payload.get("status") in HERMES_TERMINAL_STATUSES:
                    return
        finally:
            hermes_task_event_bus.unsubscribe(task_id, queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

- [ ] **Step 4: Include router in app**

Modify `backend/app/main.py` imports:

```python
from app.api.hermes import router as hermes_router
```

In `create_app()`, after existing API routers:

```python
    app.include_router(hermes_router)
```

- [ ] **Step 5: Run API tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q tests/test_hermes_api.py
```

Expected: tests pass. If `create_app()` starts a real runner and the test hangs, gate runner startup behind `HERMES_ENABLED` and make tests avoid executing worker work.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/hermes.py backend/app/main.py backend/tests/test_hermes_api.py
git commit -m "Expose Hermes task API"
```

---

### Task 6: Runner Lifecycle And Startup Requeue

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/hermes.py`
- Test: `backend/tests/test_hermes_api.py`

- [ ] **Step 1: Add failing startup behavior test**

Append to `backend/tests/test_hermes_api.py`:

```python
def test_create_task_enqueues_runner(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.setenv("HERMES_API_KEY", "test-hermes-key")

    enqueued: list[str] = []

    class FakeRunner:
        async def enqueue(self, task_id: str) -> None:
            enqueued.append(task_id)

    from app.api.hermes import get_hermes_runner

    app = create_app()
    app.dependency_overrides[get_hermes_runner] = lambda: FakeRunner()
    try:
        with TestClient(app) as client:
            api_key = _create_account_and_key(client)
            response = client.post(
                "/v1/hermes/tasks",
                json={"input": "run long job"},
                headers={"authorization": f"Bearer {api_key}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert enqueued == [response.json()["id"]]
```

- [ ] **Step 2: Run lifecycle test**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q tests/test_hermes_api.py::test_create_task_enqueues_runner
```

Expected: pass because `get_hermes_runner` can be overridden in tests.

- [ ] **Step 3: Wire real runner at app startup**

In `backend/app/main.py`, inside `create_app()`, after DB initialization is available and before returning `app`, add startup/shutdown handlers:

```python
    @app.on_event("startup")
    async def start_hermes_runner() -> None:
        settings = Settings()
        if not settings.hermes_enabled:
            return
        _, sessionmaker = create_engine_and_sessionmaker()
        runner = HermesTaskRunner(
            sessionmaker=sessionmaker,
            max_concurrent_tasks=settings.hermes_max_concurrent_tasks,
            task_max_runtime_seconds=settings.hermes_task_max_runtime_seconds,
        )
        app.state.hermes_task_runner = runner
        await runner.requeue_open_tasks()
        await runner.start()

    @app.on_event("shutdown")
    async def stop_hermes_runner() -> None:
        runner = getattr(app.state, "hermes_task_runner", None)
        if runner is not None:
            await runner.stop()
```

- [ ] **Step 4: Run lifecycle and API tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q tests/test_hermes_api.py tests/test_hermes_task_runner.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/app/api/hermes.py backend/tests/test_hermes_api.py
git commit -m "Start Hermes task runner with the app"
```

---

### Task 7: Platform Catalog, Visibility, And Billing Hooks

**Files:**
- Create: `backend/app/services/platform_catalog.py`
- Modify: `backend/app/api/admin.py`
- Modify: `backend/app/api/openai.py`
- Modify: `backend/app/api/portal.py`
- Modify: `backend/app/api/hermes.py`
- Modify: `backend/app/billing/service.py` if a small Hermes usage helper is needed
- Test: `backend/tests/test_hermes_api.py`

- [ ] **Step 1: Write failing platform visibility test**

Append to `backend/tests/test_hermes_api.py`:

```python
def test_hermes_model_appears_in_models_only_when_enabled_and_allowed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.setenv("HERMES_API_KEY", "test-hermes-key")
    monkeypatch.setenv("HERMES_MODEL", "hermes-agent")

    with TestClient(create_app()) as client:
        api_key = _create_account_and_key(client)
        models_response = client.get("/v1/models", headers={"authorization": f"Bearer {api_key}"})

    assert models_response.status_code == 200
    assert "hermes:hermes-agent" in {item["id"] for item in models_response.json()["data"]}
```

- [ ] **Step 2: Run visibility test and verify failure**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q tests/test_hermes_api.py::test_hermes_model_appears_in_models_only_when_enabled_and_allowed
```

Expected: `hermes:hermes-agent` missing.

- [ ] **Step 3: Add platform catalog helper**

Create `backend/app/services/platform_catalog.py`:

```python
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.registry.service import ProviderRegistry


def hermes_model_id(settings: Settings | None = None) -> str | None:
    settings = settings or Settings()
    if not settings.hermes_enabled:
        return None
    return f"hermes:{settings.hermes_model}"


def hermes_model_payload(settings: Settings | None = None) -> dict[str, object] | None:
    model_id = hermes_model_id(settings)
    if model_id is None:
        return None
    return {
        "id": model_id,
        "object": "model",
        "created": 0,
        "owned_by": "hermes",
    }


async def list_platform_models(session: AsyncSession, registry: ProviderRegistry | None = None) -> list[dict[str, object]]:
    registry = registry or ProviderRegistry()
    models = list(await registry.list_public_models(session))
    hermes_model = hermes_model_payload()
    if hermes_model is not None:
        models.append(hermes_model)
    return models
```

- [ ] **Step 4: Replace direct registry model listing**

In `backend/app/api/openai.py`, replace:

```python
await registry.list_public_models(session)
```

with:

```python
await list_platform_models(session, registry)
```

Import:

```python
from app.services.platform_catalog import list_platform_models
```

Make the same replacement in:

- `backend/app/api/admin.py`
- `backend/app/api/portal.py`

This keeps the existing account-level platform model visibility logic working for Hermes.

- [ ] **Step 5: Add Hermes task create visibility check**

In `backend/app/api/hermes.py`, before creating the task:

```python
from app.services.model_access import account_can_access_platform_model
from app.services.platform_catalog import hermes_model_id

model_id = hermes_model_id()
if model_id is None or not await account_can_access_platform_model(session, auth.account, model_id):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hermes task API is disabled")
```

Use a distinct detail `"Hermes model is not available"` if the API is enabled but the account cannot see it.

- [ ] **Step 6: Add minimal Hermes billing guard**

In `backend/app/api/hermes.py`, before enqueueing:

```python
from app.billing.service import billing_service

await billing_service.quote_request(
    session,
    auth.account,
    "hermes",
    settings.hermes_model,
    [{"role": "user", "content": payload.input}],
    None,
)
```

This intentionally uses existing pricing rows. If no `ModelPricingRecord(provider_name="hermes", native_model=settings.hermes_model)` exists, the API returns the existing 409 pricing error.

Final usage settlement is implemented in the next task. For this task, create-task balance protection is the acceptance criterion.

- [ ] **Step 7: Run visibility and API tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q tests/test_hermes_api.py tests/test_account_model_access.py
```

Expected: all tests pass after adding pricing rows in tests that create tasks. Update `_create_account_and_key` or each create-task test to insert `ModelPricingRecord(provider_name="hermes", native_model="hermes-agent", source_kind="manual", source_url="local", source_label="Hermes", input_price=0.01, output_price=0.01)` when exercising create-task success.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/platform_catalog.py backend/app/api/admin.py backend/app/api/openai.py backend/app/api/portal.py backend/app/api/hermes.py backend/tests/test_hermes_api.py
git commit -m "Expose Hermes as an account-visible platform model"
```

---

### Task 8: Hermes Usage Settlement

**Files:**
- Modify: `backend/app/runtime/hermes_task_runner.py`
- Test: `backend/tests/test_hermes_task_runner.py`

- [ ] **Step 1: Add failing billing settlement test**

Append to `backend/tests/test_hermes_task_runner.py`:

```python
from app.core.models import CreditLedgerRecord, ModelPricingRecord, UsageRecord


@pytest.mark.asyncio
async def test_runner_settles_successful_task_usage(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("HERMES_MODEL", "hermes-agent")
    engine, sessionmaker = create_engine_and_sessionmaker()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessionmaker() as session:
        account = AccountRecord(name="billing-acct", credit_balance=100)
        session.add(account)
        await session.flush()
        api_key = ApiKeyRecord(account_id=account.id, name="key", key_prefix="sk-bill", secret_hash="hash")
        session.add(api_key)
        session.add(
            ModelPricingRecord(
                provider_name="hermes",
                native_model="hermes-agent",
                source_kind="manual",
                source_url="local",
                source_label="Hermes",
                input_price=10.0,
                output_price=20.0,
            )
        )
        await session.commit()
        task = await create_hermes_task(
            session,
            account=account,
            api_key=api_key,
            payload=HermesTaskCreate(input_text="hello"),
        )
        await session.commit()

    runner = HermesTaskRunner(
        sessionmaker=sessionmaker,
        client_factory=lambda: FakeHermesClient(),
        max_concurrent_tasks=1,
        task_max_runtime_seconds=60,
    )
    await runner.run_task_once(task.id)

    async with sessionmaker() as session:
        usage_rows = list(await session.scalars(select(UsageRecord)))
        ledger_rows = list(await session.scalars(select(CreditLedgerRecord)))
        account_row = await session.get(AccountRecord, account.id)

    await engine.dispose()

    assert len(usage_rows) == 1
    assert usage_rows[0].provider_name == "hermes"
    assert usage_rows[0].model_id == "hermes:hermes-agent"
    assert usage_rows[0].outcome == "success"
    assert usage_rows[0].input_tokens > 0
    assert usage_rows[0].output_tokens > 0
    assert len(ledger_rows) == 1
    assert ledger_rows[0].provider_name == "hermes"
    assert ledger_rows[0].credits_delta < 0
    assert account_row is not None
    assert account_row.credit_balance < 100
```

Add imports at the top of `backend/tests/test_hermes_task_runner.py`:

```python
from sqlalchemy import select
```

- [ ] **Step 2: Run billing test and verify failure**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q tests/test_hermes_task_runner.py::test_runner_settles_successful_task_usage
```

Expected: fails because the runner completes the task without creating usage or ledger rows.

- [ ] **Step 3: Add settlement helper to runner**

In `backend/app/runtime/hermes_task_runner.py`, add imports:

```python
from app.auth.service import AuthContext
from app.billing.service import UsageSnapshot, billing_service, estimate_messages_tokens, estimate_text_tokens
from app.core.models import AccountRecord, ApiKeyRecord
```

Add helper methods inside `HermesTaskRunner`:

```python
    @staticmethod
    def _usage_from_task(task: HermesTaskRecord) -> UsageSnapshot:
        return UsageSnapshot(
            input_tokens=estimate_messages_tokens([{"role": "user", "content": task.input_text}]),
            output_tokens=estimate_text_tokens(task.output_text),
            cached_input_tokens=0,
            token_source="estimated",
        )

    async def _settle_successful_usage(self, task_id: str) -> None:
        settings = Settings()
        async with self.sessionmaker() as session:
            task = await session.get(HermesTaskRecord, task_id)
            if task is None:
                return
            account = await session.get(AccountRecord, task.account_id)
            api_key = await session.get(ApiKeyRecord, task.api_key_id)
            if account is None or api_key is None:
                task.error_code = "billing_context_missing"
                task.error_message = "Missing account or API key for Hermes task billing"
                await session.commit()
                return
            pricing = await billing_service.get_pricing(session, "hermes", settings.hermes_model)
            await billing_service.settle_inference(
                session,
                AuthContext(account=account, api_key=api_key, token=""),
                "hermes",
                f"hermes:{settings.hermes_model}",
                pricing,
                self._usage_from_task(task),
                notes=f"Hermes task {task.id}",
            )
```

Call the helper after marking the task `completed` and committing the final status:

```python
        await self._settle_successful_usage(task_id)
```

Place the call after the completion status commit so billing failure cannot hide the completed Hermes output. If billing fails because pricing is missing, let the error propagate in tests that expect pricing; production create-task already checks pricing before enqueue.

- [ ] **Step 4: Run runner tests**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q tests/test_hermes_task_runner.py
```

Expected: all runner tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/runtime/hermes_task_runner.py backend/tests/test_hermes_task_runner.py
git commit -m "Settle Hermes task usage"
```

---

### Task 9: Documentation And Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-04-27-hermes-task-api-design.md` only if implementation intentionally differs from the spec

- [ ] **Step 1: Add API examples to README**

Add a section near existing API examples:

```markdown
## Hermes Task API

When `HERMES_ENABLED=true`, the gateway exposes long-running Hermes agent jobs through `/v1/hermes/tasks`.

Create an async task:

```bash
curl -s https://openhubs.xyz/v1/hermes/tasks \
  -H "Authorization: Bearer $OPENHUBS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":"帮我分析这个仓库的风险点","metadata":{"source":"curl"}}'
```

Poll task status:

```bash
curl -s https://openhubs.xyz/v1/hermes/tasks/htask_example \
  -H "Authorization: Bearer $OPENHUBS_API_KEY"
```

Stream task events:

```bash
curl -N https://openhubs.xyz/v1/hermes/tasks/htask_example/events \
  -H "Authorization: Bearer $OPENHUBS_API_KEY"
```

Cancel a task:

```bash
curl -s -X POST https://openhubs.xyz/v1/hermes/tasks/htask_example/cancel \
  -H "Authorization: Bearer $OPENHUBS_API_KEY"
```
```

- [ ] **Step 2: Run backend verification**

Run:

```bash
cd backend
./.venv/bin/python -m pytest -q
./.venv/bin/ruff check app tests
```

Expected:

- pytest passes
- ruff passes

- [ ] **Step 3: Run frontend verification**

Run:

```bash
cd frontend
npm test -- --run
npm run build
```

Expected:

- tests pass
- build passes

- [ ] **Step 4: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 5: Commit docs**

```bash
git add README.md docs/superpowers/specs/2026-04-27-hermes-task-api-design.md
git commit -m "Document Hermes task API"
```

---

## Final Integration Checklist

- [ ] `HERMES_ENABLED=false` leaves `/v1/hermes/tasks` hidden and existing `/v1/chat/completions` unchanged.
- [ ] `HERMES_ENABLED=true` with missing `HERMES_API_KEY` fails startup in production config validation.
- [ ] `hermes:hermes-agent` appears in `/v1/models` only when enabled and allowed for the account.
- [ ] Account A cannot read, stream, or cancel Account B's Hermes task.
- [ ] Event replay with `after_seq` returns only later events.
- [ ] Disconnecting from `/events` does not cancel a running task.
- [ ] Failed Hermes stream records a failed task state.
- [ ] All tests and lint/build commands pass.

## Deployment Notes

Deploy disabled first:

```env
HERMES_ENABLED=false
```

Then configure production:

```env
HERMES_ENABLED=true
HERMES_API_BASE=http://127.0.0.1:8642/v1
HERMES_API_KEY=<server-side-hermes-api-key>
HERMES_MODEL=hermes-agent
HERMES_MAX_CONCURRENT_TASKS=2
```

Before enabling for users, create pricing:

```text
provider_name=hermes
native_model=hermes-agent
input_price=<operator chosen price per 1M input tokens>
output_price=<operator chosen price per 1M output tokens>
```

Then use admin account model visibility to grant `hermes:hermes-agent` to selected accounts.
