import asyncio
import json
from collections.abc import AsyncIterator
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import ChatRequest
from app.adapters.cli.codex import CodexCliAdapter
from app.adapters.cli.gemini import GeminiCliAdapter
from app.adapters.cli.process import ProcessCliAdapter
from app.adapters.http.openai_compatible import OpenAICompatibleHttpAdapter
from app.core.models import ProviderRecord
from app.core.settings import Settings
from app.registry.service import ProviderRegistry
from app.runtime.gemini_acp_client import GeminiAcpClient
from app.runtime.logging import elapsed_ms, log_gateway_event
from app.runtime.provider_process_pool import provider_process_pool


class ChatOrchestrator:
    def __init__(self) -> None:
        self.registry = ProviderRegistry()

    def _build_request(self, payload: dict[str, object]) -> ChatRequest:
        provider_name, provider_model = str(payload["model"]).split(":", 1)
        passthrough = {
            key: value
            for key, value in payload.items()
            if key
            not in {"model", "messages", "stream", "temperature", "top_p", "max_tokens", "stop", "_request_id"}
        }
        return ChatRequest(
            provider_name=provider_name,
            provider_model=provider_model,
            messages=list(payload["messages"]),
            stream=bool(payload.get("stream", False)),
            request_id=str(payload["_request_id"]) if payload.get("_request_id") is not None else None,
            temperature=payload.get("temperature"),
            top_p=payload.get("top_p"),
            max_tokens=payload.get("max_tokens"),
            stop=payload.get("stop"),
            provider_options=passthrough,
        )

    def _http_adapter(self, provider: ProviderRecord) -> OpenAICompatibleHttpAdapter:
        key = f"http:{provider.name}:{provider.http_base_url}:{provider.http_api_key}:{provider.http_headers_json}"
        handle = provider_process_pool.get_or_create(
            key=key,
            factory=lambda: {
                "adapter": OpenAICompatibleHttpAdapter(
                    base_url=provider.http_base_url or "",
                    api_key=provider.http_api_key,
                    headers=json.loads(provider.http_headers_json),
                )
            },
        )
        return handle.payload["adapter"]

    @staticmethod
    def _gemini_acp_pool_size() -> int:
        return max(1, Settings().gemini_acp_pool_size)

    def _gemini_acp_key(self, provider: ProviderRecord) -> str:
        pool_size = self._gemini_acp_pool_size()
        return (
            f"gemini-acp:{provider.name}:{provider.cli_command}:{provider.cli_args_json}:"
            f"{provider.cli_env_json}:{provider.cli_cwd}:pool={pool_size}"
        )

    @staticmethod
    def _new_gemini_acp_slot(provider: ProviderRecord) -> dict[str, object]:
        return {
            "client": GeminiAcpClient(
                command=provider.cli_command or "",
                args=[*json.loads(provider.cli_args_json), "--acp"],
                env=json.loads(provider.cli_env_json),
                cwd=provider.cli_cwd,
                read_timeout_seconds=30,
            ),
            "lock": asyncio.Lock(),
            "initialized": False,
            "session_id": None,
            "model_id": None,
            "waiters": 0,
        }

    def _gemini_acp_runtime(self, provider: ProviderRecord) -> dict[str, object]:
        key = self._gemini_acp_key(provider)
        handle = provider_process_pool.get_or_create(
            key=key,
            factory=lambda: {
                "slots": [self._new_gemini_acp_slot(provider) for _ in range(self._gemini_acp_pool_size())],
                "selection_lock": asyncio.Lock(),
                "next_slot": 0,
                "warmup_task": None,
            },
        )
        return handle.payload

    @staticmethod
    async def _acquire_gemini_acp_slot(
        runtime: dict[str, object],
    ) -> tuple[int, dict[str, object], float]:
        slots = runtime["slots"]
        assert isinstance(slots, list)
        assert slots
        selection_lock = runtime["selection_lock"]
        assert isinstance(selection_lock, asyncio.Lock)
        queue_started_at = perf_counter()
        selected_index = 0
        selected_slot: dict[str, object] | None = None
        selected_lock: asyncio.Lock | None = None
        should_wait = False

        async with selection_lock:
            start_index = int(runtime.get("next_slot", 0)) % len(slots)
            initialized_slots = [slot for slot in slots if isinstance(slot, dict) and slot.get("initialized")]
            scan_cold_slots = not initialized_slots
            for offset in range(len(slots)):
                index = (start_index + offset) % len(slots)
                slot = slots[index]
                assert isinstance(slot, dict)
                lock = slot["lock"]
                assert isinstance(lock, asyncio.Lock)
                if lock.locked() or not slot.get("initialized"):
                    continue
                selected_index = index
                selected_slot = slot
                selected_lock = lock
                runtime["next_slot"] = (index + 1) % len(slots)
                await lock.acquire()
                break

            if selected_slot is None and scan_cold_slots:
                for offset in range(len(slots)):
                    index = (start_index + offset) % len(slots)
                    slot = slots[index]
                    assert isinstance(slot, dict)
                    lock = slot["lock"]
                    assert isinstance(lock, asyncio.Lock)
                    if lock.locked():
                        continue
                    selected_index = index
                    selected_slot = slot
                    selected_lock = lock
                    runtime["next_slot"] = (index + 1) % len(slots)
                    await lock.acquire()
                    break

            if selected_slot is None:
                candidates: list[tuple[int, int, dict[str, object], asyncio.Lock]] = []
                for offset in range(len(slots)):
                    index = (start_index + offset) % len(slots)
                    slot = slots[index]
                    assert isinstance(slot, dict)
                    if initialized_slots and not slot.get("initialized"):
                        continue
                    lock = slot["lock"]
                    assert isinstance(lock, asyncio.Lock)
                    candidates.append((int(slot.get("waiters", 0)), index, slot, lock))
                _, selected_index, selected_slot, selected_lock = min(candidates, key=lambda candidate: candidate[0])
                selected_slot["waiters"] = int(selected_slot.get("waiters", 0)) + 1
                runtime["next_slot"] = (selected_index + 1) % len(slots)
                should_wait = True

        assert selected_slot is not None
        assert selected_lock is not None
        if should_wait:
            await selected_lock.acquire()
            selected_slot["waiters"] = max(0, int(selected_slot.get("waiters", 0)) - 1)
        return selected_index, selected_slot, elapsed_ms(queue_started_at)

    def _schedule_gemini_acp_pool_warmup(
        self,
        request: ChatRequest,
        provider: ProviderRecord,
        runtime: dict[str, object],
    ) -> None:
        if not Settings().gemini_acp_prewarm_enabled:
            return
        slots = runtime["slots"]
        assert isinstance(slots, list)
        if len(slots) <= 1 or runtime.get("warmup_task") is not None:
            return

        async def warmup() -> None:
            await self._warm_gemini_acp_idle_slots(request, provider, runtime)

        task = asyncio.create_task(warmup())
        runtime["warmup_task"] = task

        def clear_warmup(completed: asyncio.Task[None]) -> None:
            if runtime.get("warmup_task") is completed:
                runtime["warmup_task"] = None
            if completed.cancelled():
                return
            try:
                completed.result()
            except Exception as exc:
                log_gateway_event(
                    "gateway.gemini_acp.pool_warmup_failed",
                    request_id=request.request_id,
                    provider=provider.name,
                    model=f"{request.provider_name}:{request.provider_model}",
                    reason=str(exc),
                )

        task.add_done_callback(clear_warmup)

    async def _warm_gemini_acp_idle_slots(
        self,
        request: ChatRequest,
        provider: ProviderRecord,
        runtime: dict[str, object],
    ) -> None:
        slots = runtime["slots"]
        assert isinstance(slots, list)
        for slot_index, slot in enumerate(slots):
            assert isinstance(slot, dict)
            if slot.get("initialized"):
                continue
            lock = slot["lock"]
            assert isinstance(lock, asyncio.Lock)
            if lock.locked():
                continue
            await lock.acquire()
            try:
                if slot.get("initialized"):
                    continue
                client = slot["client"]
                session_id = await self._ensure_gemini_acp_session_locked(request, provider, slot, client)
                log_gateway_event(
                    "gateway.gemini_acp.pool_warmup",
                    request_id=request.request_id,
                    provider=provider.name,
                    model=f"{request.provider_name}:{request.provider_model}",
                    session_id=session_id,
                    slot_index=slot_index,
                    pool_size=len(slots),
                )
            finally:
                lock.release()

    @staticmethod
    def _gemini_acp_prompt(request: ChatRequest) -> str:
        return "\n".join(
            f"{str(message.get('role', 'user')).upper()}: {str(message.get('content', ''))}"
            for message in request.messages
        )

    @staticmethod
    def _gemini_acp_usage_payload(result: dict[str, object]) -> dict[str, object] | None:
        usage = (((result.get("_meta") or {}).get("quota") or {}).get("token_count") or {})
        if not isinstance(usage, dict):
            return None
        return {
            "prompt_tokens": int(usage.get("input_tokens") or 0),
            "completion_tokens": int(usage.get("output_tokens") or 0),
            "prompt_tokens_details": {"cached_tokens": 0},
        }

    @staticmethod
    def _gemini_acp_update_text(update: dict[str, object]) -> str:
        payload = update.get("update")
        if not isinstance(payload, dict):
            return ""
        if payload.get("sessionUpdate") != "agent_message_chunk":
            return ""
        chunk = payload.get("content")
        if isinstance(chunk, dict) and chunk.get("type") == "text":
            return str(chunk.get("text", ""))
        return ""

    async def _ensure_gemini_acp_session_locked(
        self,
        request: ChatRequest,
        provider: ProviderRecord,
        runtime: dict[str, object],
        client: GeminiAcpClient,
    ) -> str:
        if hasattr(client, "is_healthy") and not client.is_healthy():
            runtime["initialized"] = False
            runtime["session_id"] = None
            runtime["model_id"] = None
            log_gateway_event(
                "gateway.gemini_acp.session_reset",
                request_id=request.request_id,
                provider=provider.name,
                model=f"{request.provider_name}:{request.provider_model}",
                reason="client_unhealthy",
            )
        if not runtime["initialized"]:
            await client.initialize()
            runtime["initialized"] = True
            log_gateway_event(
                "gateway.gemini_acp.initialized",
                request_id=request.request_id,
                provider=provider.name,
                model=f"{request.provider_name}:{request.provider_model}",
            )
        if not runtime["session_id"]:
            session = await client.new_session(provider.cli_cwd or ".")
            runtime["session_id"] = session["sessionId"]
            runtime["model_id"] = None
            log_gateway_event(
                "gateway.gemini_acp.session_new",
                request_id=request.request_id,
                provider=provider.name,
                model=f"{request.provider_name}:{request.provider_model}",
                session_id=runtime["session_id"],
            )
        session_id = runtime["session_id"]
        assert isinstance(session_id, str)
        if runtime["session_id"] and runtime["model_id"] == request.provider_model:
            log_gateway_event(
                "gateway.gemini_acp.session_reuse",
                request_id=request.request_id,
                provider=provider.name,
                model=f"{request.provider_name}:{request.provider_model}",
                session_id=session_id,
            )
        if runtime["model_id"] != request.provider_model:
            await client.set_model(session_id, request.provider_model)
            runtime["model_id"] = request.provider_model
            log_gateway_event(
                "gateway.gemini_acp.model_set",
                request_id=request.request_id,
                provider=provider.name,
                model=f"{request.provider_name}:{request.provider_model}",
                session_id=session_id,
            )
        return session_id

    def _cli_adapter(self, provider: ProviderRecord):
        if provider.name == "codex":
            key = f"cli:{provider.name}:{provider.cli_command}:{provider.cli_args_json}:{provider.cli_env_json}:{provider.cli_cwd}"
            handle = provider_process_pool.get_or_create(
                key=key,
                factory=lambda: {
                    "adapter": CodexCliAdapter(
                        command=provider.cli_command or "",
                        args=json.loads(provider.cli_args_json),
                        env=json.loads(provider.cli_env_json),
                        cwd=provider.cli_cwd,
                        read_timeout_seconds=30,
                    )
                },
            )
            return handle.payload["adapter"]
        if provider.name == "gemini":
            key = f"cli:{provider.name}:{provider.cli_command}:{provider.cli_args_json}:{provider.cli_env_json}:{provider.cli_cwd}"
            handle = provider_process_pool.get_or_create(
                key=key,
                factory=lambda: {
                    "adapter": GeminiCliAdapter(
                        command=provider.cli_command or "",
                        args=json.loads(provider.cli_args_json),
                        env=json.loads(provider.cli_env_json),
                        cwd=provider.cli_cwd,
                        read_timeout_seconds=30,
                    )
                },
            )
            return handle.payload["adapter"]
        key = f"cli:{provider.name}:{provider.cli_command}:{provider.cli_args_json}:{provider.cli_env_json}:{provider.cli_cwd}"
        handle = provider_process_pool.get_or_create(
            key=key,
            factory=lambda: {
                "adapter": ProcessCliAdapter(
                    command=provider.cli_command or "",
                    args=json.loads(provider.cli_args_json),
                    env=json.loads(provider.cli_env_json),
                    cwd=provider.cli_cwd,
                    read_timeout_seconds=30,
                )
            },
        )
        return handle.payload["adapter"]

    async def _gemini_acp_chat(self, request: ChatRequest, provider: ProviderRecord) -> dict[str, object]:
        runtime = self._gemini_acp_runtime(provider)
        slot_index, slot, queue_wait_ms = await self._acquire_gemini_acp_slot(runtime)
        client = slot["client"]
        lock = slot["lock"]
        assert isinstance(lock, asyncio.Lock)
        slots = runtime["slots"]
        assert isinstance(slots, list)
        try:
            log_gateway_event(
                "gateway.gemini_acp.queue_wait",
                request_id=request.request_id,
                provider=provider.name,
                model=f"{request.provider_name}:{request.provider_model}",
                queued=slot["waiters"],
                slot_index=slot_index,
                pool_size=len(slots),
                elapsed_ms=queue_wait_ms,
            )
            session_id = await self._ensure_gemini_acp_session_locked(request, provider, slot, client)
            prompt = self._gemini_acp_prompt(request)
            prompt_started_at = perf_counter()
            prompt_result = await client.prompt(session_id, prompt)
            log_gateway_event(
                "gateway.gemini_acp.prompt_complete",
                request_id=request.request_id,
                provider=provider.name,
                model=f"{request.provider_name}:{request.provider_model}",
                session_id=session_id,
                elapsed_ms=elapsed_ms(prompt_started_at),
            )
            self._schedule_gemini_acp_pool_warmup(request, provider, runtime)
        finally:
            lock.release()

        content_parts: list[str] = []
        for update in prompt_result.updates:
            content_parts.append(self._gemini_acp_update_text(update))
        usage_payload = self._gemini_acp_usage_payload(prompt_result.result)
        return {
            "id": session_id,
            "object": "chat.completion",
            "model": f"{request.provider_name}:{request.provider_model}",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "".join(content_parts)},
                    "finish_reason": "stop",
                }
            ],
            **({"usage": usage_payload} if usage_payload is not None else {}),
        }

    async def _gemini_acp_stream_chat(self, request: ChatRequest, provider: ProviderRecord) -> AsyncIterator[str]:
        runtime = self._gemini_acp_runtime(provider)
        slot_index, slot, queue_wait_ms = await self._acquire_gemini_acp_slot(runtime)
        client = slot["client"]
        lock = slot["lock"]
        assert isinstance(lock, asyncio.Lock)
        slots = runtime["slots"]
        assert isinstance(slots, list)
        try:
            log_gateway_event(
                "gateway.gemini_acp.queue_wait",
                request_id=request.request_id,
                provider=provider.name,
                model=f"{request.provider_name}:{request.provider_model}",
                queued=slot["waiters"],
                slot_index=slot_index,
                pool_size=len(slots),
                elapsed_ms=queue_wait_ms,
            )
            session_id = await self._ensure_gemini_acp_session_locked(request, provider, slot, client)
            prompt = self._gemini_acp_prompt(request)
            prompt_started_at = perf_counter()
            async for event in client.prompt_stream(session_id, prompt):
                if event.update is not None:
                    text = self._gemini_acp_update_text(event.update)
                    if not text:
                        continue
                    payload = {
                        "id": session_id,
                        "object": "chat.completion.chunk",
                        "model": f"{request.provider_name}:{request.provider_model}",
                        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                if event.result is not None:
                    finish_payload = {
                        "id": session_id,
                        "object": "chat.completion.chunk",
                        "model": f"{request.provider_name}:{request.provider_model}",
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    }
                    usage_payload = self._gemini_acp_usage_payload(event.result)
                    if usage_payload is not None:
                        finish_payload["usage"] = usage_payload
                    yield f"data: {json.dumps(finish_payload)}\n\n"
                    log_gateway_event(
                        "gateway.gemini_acp.prompt_complete",
                        request_id=request.request_id,
                        provider=provider.name,
                        model=f"{request.provider_name}:{request.provider_model}",
                        session_id=session_id,
                        elapsed_ms=elapsed_ms(prompt_started_at),
                    )
                    self._schedule_gemini_acp_pool_warmup(request, provider, runtime)
            yield "data: [DONE]\n\n"
        finally:
            lock.release()

    async def prepare(
        self,
        payload: dict[str, object],
        session: AsyncSession,
    ) -> tuple[ChatRequest, ProviderRecord]:
        request = self._build_request(payload)
        provider = await self.registry.get_provider(session, request.provider_name)
        if request.provider_model == "default":
            request.provider_model = provider.exposed_model
        return request, provider

    async def run(self, payload: dict[str, object], session: AsyncSession) -> dict[str, object]:
        request, provider = await self.prepare(payload, session)
        if provider.route_policy in {"cli-first", "fixed-cli"}:
            if provider.name == "gemini" and not request.stream and Settings().gemini_acp_enabled:
                for attempt in range(2):
                    try:
                        return await self._gemini_acp_chat(request, provider)
                    except Exception as exc:
                        provider_process_pool.invalidate(self._gemini_acp_key(provider))
                        if attempt == 0:
                            log_gateway_event(
                                "gateway.gemini_acp.retry",
                                request_id=request.request_id,
                                provider=provider.name,
                                model=f"{request.provider_name}:{request.provider_model}",
                                reason=str(exc),
                            )
                            continue
                        log_gateway_event(
                            "gateway.gemini_acp.fallback",
                            request_id=request.request_id,
                            provider=provider.name,
                            model=f"{request.provider_name}:{request.provider_model}",
                            reason=str(exc),
                        )
            return await self._cli_adapter(provider).chat(request)
        return await self._http_adapter(provider).chat(request)

    async def stream_prepared(
        self,
        request: ChatRequest,
        provider: ProviderRecord,
    ) -> AsyncIterator[str]:
        if provider.route_policy in {"cli-first", "fixed-cli"}:
            if provider.name == "gemini" and Settings().gemini_acp_enabled:
                for attempt in range(2):
                    emitted = False
                    try:
                        async for chunk in self._gemini_acp_stream_chat(request, provider):
                            emitted = True
                            yield chunk
                        return
                    except Exception as exc:
                        provider_process_pool.invalidate(self._gemini_acp_key(provider))
                        if emitted:
                            log_gateway_event(
                                "gateway.gemini_acp.fallback",
                                request_id=request.request_id,
                                provider=provider.name,
                                model=f"{request.provider_name}:{request.provider_model}",
                                reason=str(exc),
                            )
                            raise
                        if attempt == 0:
                            log_gateway_event(
                                "gateway.gemini_acp.retry",
                                request_id=request.request_id,
                                provider=provider.name,
                                model=f"{request.provider_name}:{request.provider_model}",
                                reason=str(exc),
                            )
                            continue
                        log_gateway_event(
                            "gateway.gemini_acp.fallback",
                            request_id=request.request_id,
                            provider=provider.name,
                            model=f"{request.provider_name}:{request.provider_model}",
                            reason=str(exc),
                        )
                        break
            async for chunk in self._cli_adapter(provider).stream_chat(request):
                yield chunk
            return
        async for chunk in self._http_adapter(provider).stream_chat(request):
            yield chunk

    async def stream(
        self,
        payload: dict[str, object],
        session: AsyncSession,
    ) -> AsyncIterator[str]:
        request, provider = await self.prepare(payload, session)
        async for chunk in self.stream_prepared(request, provider):
            yield chunk
