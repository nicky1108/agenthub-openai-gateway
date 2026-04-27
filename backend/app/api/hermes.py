from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthContext, require_api_key
from app.billing.service import billing_service
from app.core.db import get_session
from app.core.models import HermesTaskRecord
from app.core.settings import Settings
from app.services.model_access import account_can_access_platform_model
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
from app.services.platform_catalog import hermes_model_id

router = APIRouter(prefix="/v1/hermes", tags=["hermes"])


def get_settings() -> Settings:
    return Settings()


def require_hermes_enabled(settings: Settings = Depends(get_settings)) -> Settings:
    if not settings.hermes_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hermes task API is disabled",
        )
    if not settings.hermes_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hermes API key is not configured",
        )
    return settings


def get_hermes_runner(request: Request):
    return getattr(request.app.state, "hermes_task_runner", None)


class HermesTaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str
    conversation: str | None = None
    previous_response_id: str | None = None
    instructions: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
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


def _enforce_payload_limits(payload: HermesTaskCreateRequest, settings: Settings) -> None:
    if len(payload.input) > settings.hermes_input_max_chars:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Hermes input is too large",
        )
    metadata_bytes = len(json.dumps(payload.metadata, ensure_ascii=False).encode("utf-8"))
    if metadata_bytes > settings.hermes_metadata_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Hermes metadata is too large",
        )


def sse_event(event_type: str, seq: int, payload: dict[str, Any]) -> str:
    return f"event: {event_type}\nid: {seq}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _event_payload(event_payload_json: str) -> dict[str, Any]:
    try:
        payload = json.loads(event_payload_json)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


@router.post("/tasks", response_model=HermesTaskRead, status_code=status.HTTP_202_ACCEPTED)
async def create_task(
    payload: HermesTaskCreateRequest,
    settings: Settings = Depends(require_hermes_enabled),
    runner=Depends(get_hermes_runner),
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_key),
) -> HermesTaskRead:
    _enforce_payload_limits(payload, settings)
    model_id = hermes_model_id(settings)
    if model_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hermes task API is disabled",
        )
    if not await account_can_access_platform_model(session, auth.account, model_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hermes model is not available",
        )
    billing_service.require_credit_balance(auth.account, settings.hermes_task_start_credits)
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
    usage = await billing_service.record_fixed_credit_charge(
        session,
        auth,
        "hermes",
        model_id,
        credits=settings.hermes_task_start_credits,
        entry_type="hermes_task_start",
        token_source="hermes_start_fee",
        outcome="accepted",
        notes=f"Hermes task {task.id} start fee",
    )
    task.start_usage_record_id = usage.id
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
        task.updated_at = datetime.now(timezone.utc)
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
        queue = hermes_task_event_bus.subscribe(task_id)
        try:
            stored_events = await list_hermes_task_events(session, task_id, after_seq=current_after_seq)
            for event in stored_events:
                current_after_seq = event.seq
                yield sse_event(event.event_type, event.seq, _event_payload(event.payload_json))
            if task.status in HERMES_TERMINAL_STATUSES:
                return
            while True:
                message = await queue.get()
                if message.seq <= current_after_seq:
                    continue
                current_after_seq = message.seq
                yield sse_event(message.event_type, message.seq, message.payload)
                if (
                    message.event_type == "task.status"
                    and message.payload.get("status") in HERMES_TERMINAL_STATUSES
                ):
                    return
        finally:
            hermes_task_event_bus.unsubscribe(task_id, queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
