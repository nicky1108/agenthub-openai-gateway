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
