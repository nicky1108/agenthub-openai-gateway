from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.adapters.base import ChatRequest


class OpenAICompatibleHttpAdapter:
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        headers: dict[str, str],
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
    ) -> None:
        merged_headers = dict(headers)
        if api_key:
            merged_headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=merged_headers,
            transport=transport,
        )

    async def chat(self, request: ChatRequest) -> dict[str, Any]:
        response = await self._client.post(
            "/v1/chat/completions",
            json={
                "model": request.provider_model,
                "messages": request.messages,
                "stream": False,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "max_tokens": request.max_tokens,
                "stop": request.stop,
                **request.provider_options,
            },
        )
        response.raise_for_status()
        return response.json()

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[str]:
        async with self._client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": request.provider_model,
                "messages": request.messages,
                "stream": True,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "max_tokens": request.max_tokens,
                "stop": request.stop,
                **request.provider_options,
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    yield f"{line}\n"
                else:
                    yield "\n"
