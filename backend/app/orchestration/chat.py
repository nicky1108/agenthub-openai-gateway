from app.adapters.base import ChatRequest
from app.adapters.http.base import MockHttpAdapter


class ChatOrchestrator:
    def __init__(self) -> None:
        self.http_adapter = MockHttpAdapter()

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
        return await self.http_adapter.chat(request)
