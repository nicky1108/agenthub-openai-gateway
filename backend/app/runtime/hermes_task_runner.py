from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.models import HermesTaskRecord
from app.core.settings import Settings
from app.runtime.logging import log_gateway_event
from app.services.hermes_client import (
    HermesApiError,
    HermesClient,
    HermesRequest,
    extract_hermes_output_text,
)
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
        sessionmaker: async_sessionmaker[AsyncSession],
        client_factory: Callable[[], Any] = build_hermes_client,
        max_concurrent_tasks: int = 2,
        task_max_runtime_seconds: float = 7200.0,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.client_factory = client_factory
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.max_concurrent_tasks = max(1, max_concurrent_tasks)
        self.semaphore = asyncio.Semaphore(self.max_concurrent_tasks)
        self.task_max_runtime_seconds = task_max_runtime_seconds
        self._workers: list[asyncio.Task[None]] = []
        self._stopped = asyncio.Event()

    async def enqueue(self, task_id: str) -> None:
        await self.queue.put(task_id)

    async def start(self, worker_count: int | None = None) -> None:
        if self._workers:
            return
        count = worker_count or self.max_concurrent_tasks
        self._stopped.clear()
        for _ in range(max(1, count)):
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
                    .where(
                        HermesTaskRecord.status.in_(
                            [
                                HERMES_STATUS_QUEUED,
                                HERMES_STATUS_RUNNING,
                                HERMES_STATUS_CANCEL_REQUESTED,
                            ]
                        )
                    )
                    .order_by(HermesTaskRecord.created_at.asc())
                )
            )
        for row in rows:
            await self.enqueue(row.id)

    async def run_task_once(self, task_id: str) -> None:
        started_at = datetime.now(timezone.utc)
        output_chunks: list[str] = []
        response_id: str | None = None

        request = await self._mark_running(task_id, started_at)
        if request is None:
            return

        try:
            client = self.client_factory()
            async with asyncio.timeout(self.task_max_runtime_seconds):
                async for event in client.stream_response(request):
                    async with self.sessionmaker() as session:
                        task = await session.get(HermesTaskRecord, task_id)
                        if task is None:
                            return
                        if task.status == HERMES_STATUS_CANCEL_REQUESTED:
                            await self._mark_cancelled(session, task)
                            await session.commit()
                            return
                        if event.type == "response.output_text.delta":
                            delta = str(event.payload.get("delta") or "")
                            output_chunks.append(delta)
                            task.output_text = "".join(output_chunks)
                        if event.type == "response.completed":
                            response = event.payload.get("response")
                            if isinstance(response, dict):
                                response_id = str(response.get("id") or "") or None
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

        await self._mark_completed(task_id, response_id, output_chunks)

    async def _mark_running(self, task_id: str, started_at: datetime) -> HermesRequest | None:
        async with self.sessionmaker() as session:
            task = await session.get(HermesTaskRecord, task_id)
            if task is None:
                return None
            if task.status == HERMES_STATUS_CANCEL_REQUESTED:
                await self._mark_cancelled(session, task)
                await session.commit()
                return None
            task.status = HERMES_STATUS_RUNNING
            task.started_at = task.started_at or started_at
            task.updated_at = started_at
            await append_hermes_task_event(
                session,
                task_id=task.id,
                event_type="task.status",
                payload={"status": task.status},
            )
            request = HermesRequest(
                input_text=task.input_text,
                conversation=task.conversation,
                previous_response_id=task.previous_response_id,
                instructions=task.instructions,
                metadata=self._decode_metadata(task.metadata_json),
            )
            await session.commit()
            return request

    async def _mark_completed(
        self,
        task_id: str,
        response_id: str | None,
        output_chunks: list[str],
    ) -> None:
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
            await append_hermes_task_event(
                session,
                task_id=task.id,
                event_type="task.status",
                payload={"status": task.status},
            )
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
            log_gateway_event(
                "gateway.hermes.task.failed",
                task_id=task.id,
                account_id=task.account_id,
                error_code=error_code,
            )

    async def _mark_cancelled(self, session: AsyncSession, task: HermesTaskRecord) -> None:
        now = datetime.now(timezone.utc)
        task.status = HERMES_STATUS_CANCELLED
        task.completed_at = now
        task.updated_at = now
        await append_hermes_task_event(
            session,
            task_id=task.id,
            event_type="task.status",
            payload={"status": task.status},
        )

    @staticmethod
    def _decode_metadata(value: str) -> dict[str, Any]:
        try:
            decoded = json.loads(value or "{}")
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
