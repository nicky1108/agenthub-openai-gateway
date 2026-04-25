from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

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
        self._base_url = base_url.rstrip("/")
        normalized_path = urlparse(self._base_url).path.rstrip("/")
        self._chat_completions_path = "/chat/completions" if normalized_path.endswith("/v1") else "/v1/chat/completions"
        self._headers = merged_headers
        self._transport = transport

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            transport=self._transport,
        ) as client:
            yield client

    async def chat(self, request: ChatRequest) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.post(
                self._chat_completions_path,
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
        async with self._client() as client:
            async with client.stream(
                "POST",
                self._chat_completions_path,
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
