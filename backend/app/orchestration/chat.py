from app.adapters.base import ChatRequest
from app.adapters.cli.base import MockCliAdapter
from app.adapters.http.base import MockHttpAdapter


class ChatOrchestrator:
    def __init__(self) -> None:
        self.http_adapter = MockHttpAdapter()
        self.cli_adapter = MockCliAdapter()

    async def run(self, payload: dict[str, object]) -> dict[str, object]:
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
        if provider_name == "gemini":
            route_policy = "cli-first"

        if route_policy == "cli-first":
            return await self.cli_adapter.chat(request)
        return await self.http_adapter.chat(request)
