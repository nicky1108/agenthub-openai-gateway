from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import ChatRequest
from app.adapters.cli.base import MockCliAdapter
from app.adapters.http.base import MockHttpAdapter
from app.core.models import ProviderRecord


class ChatOrchestrator:
    def __init__(self) -> None:
        self.http_adapter = MockHttpAdapter()
        self.cli_adapter = MockCliAdapter()

    def _build_request(self, payload: dict[str, object]) -> ChatRequest:
        provider_name, provider_model = str(payload["model"]).split(":", 1)
        return ChatRequest(
            provider_name=provider_name,
            provider_model=provider_model,
            messages=list(payload["messages"]),
            stream=bool(payload.get("stream", False)),
            temperature=payload.get("temperature"),
            top_p=payload.get("top_p"),
            max_tokens=payload.get("max_tokens"),
            stop=payload.get("stop"),
        )

    async def _route_policy(self, provider_name: str, session: AsyncSession) -> str:
        route_policy = "http-first"
        provider = await session.scalar(
            select(ProviderRecord).where(ProviderRecord.name == provider_name)
        )
        if provider is not None:
            route_policy = provider.route_policy
        return route_policy

    async def run(self, payload: dict[str, object], session: AsyncSession) -> dict[str, object]:
        request = self._build_request(payload)
        if await self._route_policy(request.provider_name, session) == "cli-first":
            return await self.cli_adapter.chat(request)
        return await self.http_adapter.chat(request)

    async def stream(
        self,
        payload: dict[str, object],
        session: AsyncSession,
    ) -> AsyncIterator[str]:
        request = self._build_request(payload)
        if await self._route_policy(request.provider_name, session) == "cli-first":
            async for chunk in self.cli_adapter.stream_chat(request):
                yield chunk
            return
        async for chunk in self.http_adapter.stream_chat(request):
            yield chunk
