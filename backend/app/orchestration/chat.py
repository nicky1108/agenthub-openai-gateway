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

    def _gemini_acp_key(self, provider: ProviderRecord) -> str:
        return f"gemini-acp:{provider.name}:{provider.cli_command}:{provider.cli_args_json}:{provider.cli_env_json}:{provider.cli_cwd}"

    def _gemini_acp_runtime(self, provider: ProviderRecord) -> dict[str, object]:
        key = self._gemini_acp_key(provider)
        handle = provider_process_pool.get_or_create(
            key=key,
            factory=lambda: {
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
            },
        )
        return handle.payload

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
        client = runtime["client"]
        lock = runtime["lock"]
        assert isinstance(lock, asyncio.Lock)
        queue_started_at = perf_counter()
        runtime["waiters"] = int(runtime.get("waiters", 0)) + 1
        async with lock:
            runtime["waiters"] = max(0, int(runtime.get("waiters", 0)) - 1)
            log_gateway_event(
                "gateway.gemini_acp.queue_wait",
                request_id=request.request_id,
                provider=provider.name,
                model=f"{request.provider_name}:{request.provider_model}",
                queued=runtime["waiters"],
                elapsed_ms=elapsed_ms(queue_started_at),
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
            prompt = "\n".join(
                f"{str(message.get('role', 'user')).upper()}: {str(message.get('content', ''))}"
                for message in request.messages
            )
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

        content_parts: list[str] = []
        for update in prompt_result.updates:
            payload = update.get("update")
            if not isinstance(payload, dict):
                continue
            if payload.get("sessionUpdate") != "agent_message_chunk":
                continue
            chunk = payload.get("content")
            if isinstance(chunk, dict) and chunk.get("type") == "text":
                content_parts.append(str(chunk.get("text", "")))
        usage = (((prompt_result.result.get("_meta") or {}).get("quota") or {}).get("token_count") or {})
        usage_payload = None
        if isinstance(usage, dict):
            usage_payload = {
                "prompt_tokens": int(usage.get("input_tokens") or 0),
                "completion_tokens": int(usage.get("output_tokens") or 0),
                "prompt_tokens_details": {"cached_tokens": 0},
            }
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
                try:
                    return await self._gemini_acp_chat(request, provider)
                except Exception as exc:
                    provider_process_pool.invalidate(self._gemini_acp_key(provider))
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
