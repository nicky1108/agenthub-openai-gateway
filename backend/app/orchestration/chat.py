from app.adapters.base import ChatRequest
from app.adapters.cli.base import MockCliAdapter
from app.adapters.http.base import MockHttpAdapter
from app.core.models import ProviderRecord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class ChatOrchestrator:
    def __init__(self) -> None:
        self.http_adapter = MockHttpAdapter()
        self.cli_adapter = MockCliAdapter()

    async def run(self, payload: dict[str, object], session: AsyncSession) -> dict[str, object]:
        provider_name, provider_model = str(payload["model"]).split(":", 1)
        request = ChatRequest(
            provider_name=provider_name,
            provider_model=provider_model,
            messages=list(payload["messages"]),
            stream=bool(payload.get("stream", False)),
            temperature=payload.get("temperature"),
            top_p=payload.get("top_p"),
            max_tokens=payload.get("max_tokens"),
            stop=payload.get("stop"),
        )

        route_policy = "http-first"
        provider = await session.scalar(
            select(ProviderRecord).where(ProviderRecord.name == provider_name)
        )
        if provider is not None:
            route_policy = provider.route_policy

        if route_policy == "cli-first":
            return await self.cli_adapter.chat(request)
        return await self.http_adapter.chat(request)
