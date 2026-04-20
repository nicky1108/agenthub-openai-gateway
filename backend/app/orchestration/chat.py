import json
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import ChatRequest
from app.adapters.cli.gemini import GeminiCliAdapter
from app.adapters.cli.process import ProcessCliAdapter
from app.adapters.http.openai_compatible import OpenAICompatibleHttpAdapter
from app.core.models import ProviderRecord
from app.registry.service import ProviderRegistry


class ChatOrchestrator:
    def __init__(self) -> None:
        self.registry = ProviderRegistry()

    def _build_request(self, payload: dict[str, object]) -> ChatRequest:
        provider_name, provider_model = str(payload["model"]).split(":", 1)
        passthrough = {
            key: value
            for key, value in payload.items()
            if key
            not in {"model", "messages", "stream", "temperature", "top_p", "max_tokens", "stop"}
        }
        return ChatRequest(
            provider_name=provider_name,
            provider_model=provider_model,
            messages=list(payload["messages"]),
            stream=bool(payload.get("stream", False)),
            temperature=payload.get("temperature"),
            top_p=payload.get("top_p"),
            max_tokens=payload.get("max_tokens"),
            stop=payload.get("stop"),
            provider_options=passthrough,
        )

    def _http_adapter(self, provider: ProviderRecord) -> OpenAICompatibleHttpAdapter:
        return OpenAICompatibleHttpAdapter(
            base_url=provider.http_base_url or "",
            api_key=provider.http_api_key,
            headers=json.loads(provider.http_headers_json),
        )

    def _cli_adapter(self, provider: ProviderRecord):
        if provider.name == "gemini":
            return GeminiCliAdapter(
                command=provider.cli_command or "",
                args=json.loads(provider.cli_args_json),
                env=json.loads(provider.cli_env_json),
                cwd=provider.cli_cwd,
                read_timeout_seconds=30,
            )
        return ProcessCliAdapter(
            command=provider.cli_command or "",
            args=json.loads(provider.cli_args_json),
            env=json.loads(provider.cli_env_json),
            cwd=provider.cli_cwd,
            read_timeout_seconds=30,
        )

    async def prepare(
        self,
        payload: dict[str, object],
        session: AsyncSession,
    ) -> tuple[ChatRequest, ProviderRecord]:
        request = self._build_request(payload)
        provider = await self.registry.get_provider(session, request.provider_name)
        return request, provider

    async def run(self, payload: dict[str, object], session: AsyncSession) -> dict[str, object]:
        request, provider = await self.prepare(payload, session)
        if provider.route_policy in {"cli-first", "fixed-cli"}:
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
