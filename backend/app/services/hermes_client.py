from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx


class HermesApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class HermesRequest:
    input_text: str
    conversation: str
    previous_response_id: str | None = None
    instructions: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HermesResponseEvent:
    type: str
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.type:
            raise ValueError("event type is required")


def extract_hermes_output_text(response: dict[str, Any]) -> str:
    output = response.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                        text = content.get("text")
                        if text:
                            chunks.append(str(text))
            elif item.get("type") == "output_text":
                text = item.get("text")
                if text:
                    chunks.append(str(text))
        if chunks:
            return "\n".join(chunks).strip()
    if isinstance(response.get("output_text"), str):
        return str(response["output_text"]).strip()
    return ""


class HermesClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        request_timeout_seconds: float = 60.0,
        stream_read_timeout_seconds: float = 1800.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.request_timeout_seconds = request_timeout_seconds
        self.stream_read_timeout_seconds = stream_read_timeout_seconds
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _payload(self, request: HermesRequest, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": request.input_text,
            "store": True,
            "stream": stream,
        }
        if request.previous_response_id:
            payload["previous_response_id"] = request.previous_response_id
        else:
            payload["conversation"] = request.conversation
        if request.instructions:
            payload["instructions"] = request.instructions
        if request.metadata:
            payload["metadata"] = request.metadata
        return payload

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self.request_timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.get(f"{self.base_url}/health", headers=self._headers())
        if response.status_code >= 400:
            raise HermesApiError(response.text, status_code=response.status_code)
        parsed = response.json() if response.content else {}
        return parsed if isinstance(parsed, dict) else {}

    async def create_response(self, request: HermesRequest) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self.request_timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.post(
                f"{self.base_url}/responses",
                headers=self._headers(),
                json=self._payload(request, stream=False),
            )
        if response.status_code >= 400:
            raise HermesApiError(response.text, status_code=response.status_code)
        parsed = response.json() if response.content else {}
        if not isinstance(parsed, dict):
            raise HermesApiError("Unexpected Hermes API response shape")
        return parsed

    async def stream_response(self, request: HermesRequest) -> AsyncIterator[HermesResponseEvent]:
        timeout = httpx.Timeout(
            connect=self.request_timeout_seconds,
            read=self.stream_read_timeout_seconds,
            write=self.request_timeout_seconds,
            pool=self.request_timeout_seconds,
        )
        async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/responses",
                headers=self._headers(),
                json=self._payload(request, stream=True),
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise HermesApiError(body.decode("utf-8", errors="replace"), status_code=response.status_code)
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    raw = await response.aread()
                    parsed = json.loads(raw.decode("utf-8")) if raw else {}
                    if isinstance(parsed, dict):
                        yield HermesResponseEvent(
                            type="response.completed",
                            payload={"response": parsed},
                        )
                    return
                async for raw_line in response.aiter_lines():
                    line = (raw_line or "").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    event = json.loads(data)
                    if not isinstance(event, dict):
                        continue
                    event_type = str(event.get("type") or "")
                    if event_type == "response.output_text.delta":
                        yield HermesResponseEvent(type=event_type, payload={"delta": str(event.get("delta") or "")})
                        continue
                    yield HermesResponseEvent(type=event_type, payload=event)
