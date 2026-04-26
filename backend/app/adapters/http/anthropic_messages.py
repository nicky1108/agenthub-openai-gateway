from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from app.adapters.base import ChatRequest

DEFAULT_HTTP_TIMEOUT = httpx.Timeout(60.0, connect=10.0, write=30.0, pool=10.0)


def _normalized_anthropic_base_url(base_url: str) -> str:
    parsed = urlparse(base_url.rstrip("/"))
    normalized_path = parsed.path.rstrip("/")
    if parsed.hostname == "api.yourouter.ai" and normalized_path == "/anthropic":
        return urlunparse((parsed.scheme, parsed.netloc, "", "", "", "")).rstrip("/")
    return base_url.rstrip("/")


def _messages_path_for_base_url(base_url: str) -> str:
    normalized_path = urlparse(base_url.rstrip("/")).path.rstrip("/")
    return "/messages" if normalized_path.endswith("/v1") else "/v1/messages"


def _models_path_for_base_url(base_url: str) -> str:
    normalized_path = urlparse(base_url.rstrip("/")).path.rstrip("/")
    return "/models" if normalized_path.endswith("/v1") else "/v1/models"


def _anthropic_system_prompt(messages: list[dict[str, Any]]) -> str | None:
    system_parts: list[str] = []
    for message in messages:
        if message.get("role") != "system":
            continue
        content = message.get("content")
        if isinstance(content, str) and content:
            system_parts.append(content)
    if not system_parts:
        return None
    return "\n\n".join(system_parts)


def _anthropic_content(content: Any) -> Any:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    blocks: list[dict[str, Any]] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
            blocks.append({"type": "text", "text": item["text"]})
        elif isinstance(item, dict):
            blocks.append(item)
        elif isinstance(item, str):
            blocks.append({"type": "text", "text": item})
    return blocks or ""


def _anthropic_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        if role not in {"user", "assistant"}:
            continue
        converted.append({"role": role, "content": _anthropic_content(message.get("content"))})
    return converted


def _anthropic_stop_sequences(stop: Any) -> list[str] | None:
    if isinstance(stop, str) and stop:
        return [stop]
    if isinstance(stop, list):
        values = [item for item in stop if isinstance(item, str) and item]
        return values or None
    return None


def _openai_finish_reason(stop_reason: str | None) -> str | None:
    if stop_reason in {"end_turn", "stop_sequence"}:
        return "stop"
    if stop_reason == "max_tokens":
        return "length"
    if stop_reason == "tool_use":
        return "tool_calls"
    return None


def _extract_text_from_anthropic_content(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


class AnthropicMessagesAdapter:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        headers: dict[str, str],
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> None:
        merged_headers = dict(headers)
        merged_headers["Authorization"] = f"Bearer {api_key}"
        merged_headers["x-api-key"] = api_key
        merged_headers.setdefault("anthropic-version", "2023-06-01")
        merged_headers.setdefault("vendor", "anthropic")
        self._base_url = _normalized_anthropic_base_url(base_url)
        self._messages_path = _messages_path_for_base_url(self._base_url)
        self._models_path = _models_path_for_base_url(self._base_url)
        self._headers = merged_headers
        self._transport = transport
        self._timeout = timeout or DEFAULT_HTTP_TIMEOUT

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            transport=self._transport,
            timeout=self._timeout,
        ) as client:
            yield client

    def _request_body(self, request: ChatRequest, *, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": request.provider_model,
            "messages": _anthropic_messages(request.messages),
            "max_tokens": request.max_tokens or 1024,
            "stream": stream,
            **request.provider_options,
        }
        system_prompt = _anthropic_system_prompt(request.messages)
        if system_prompt is not None:
            body["system"] = system_prompt
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.top_p is not None:
            body["top_p"] = request.top_p
        stop_sequences = _anthropic_stop_sequences(request.stop)
        if stop_sequences is not None:
            body["stop_sequences"] = stop_sequences
        return body

    async def list_models(self) -> list[str]:
        async with self._client() as client:
            response = await client.get(self._models_path)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            return []
        return [
            item["id"]
            for item in payload["data"]
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]

    async def chat(self, request: ChatRequest) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.post(self._messages_path, json=self._request_body(request, stream=False))
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("anthropic provider returned invalid response")
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        return {
            "id": payload.get("id", "msg_custom"),
            "object": "chat.completion",
            "model": f"{request.provider_name}:{request.provider_model}",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": _extract_text_from_anthropic_content(payload.get("content")),
                    },
                    "finish_reason": _openai_finish_reason(payload.get("stop_reason")),
                }
            ],
            "usage": {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            },
        }

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[str]:
        async with self._client() as client:
            async with client.stream(
                "POST",
                self._messages_path,
                json=self._request_body(request, stream=True),
            ) as response:
                response.raise_for_status()
                message_id = "msg_custom"
                usage: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0}
                stop_reason: str | None = None
                emitted_role = False

                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line or line.startswith("event:") or not line.startswith("data:"):
                        continue
                    payload_text = line.removeprefix("data:").strip()
                    if payload_text == "[DONE]":
                        continue
                    try:
                        payload = json.loads(payload_text)
                    except ValueError:
                        continue
                    if not isinstance(payload, dict):
                        continue

                    event_type = payload.get("type")
                    if event_type == "message_start":
                        message = payload.get("message")
                        if isinstance(message, dict):
                            if isinstance(message.get("id"), str):
                                message_id = message["id"]
                            if isinstance(message.get("usage"), dict):
                                usage = message["usage"]
                        continue
                    if event_type == "message_delta":
                        delta = payload.get("delta")
                        if isinstance(delta, dict) and isinstance(delta.get("stop_reason"), str):
                            stop_reason = delta["stop_reason"]
                        if isinstance(payload.get("usage"), dict):
                            usage = payload["usage"]
                        continue
                    if event_type == "content_block_delta":
                        delta = payload.get("delta")
                        if not isinstance(delta, dict) or delta.get("type") != "text_delta":
                            continue
                        text = delta.get("text")
                        if not isinstance(text, str) or not text:
                            continue
                        chunk = {
                            "id": message_id,
                            "object": "chat.completion.chunk",
                            "model": f"{request.provider_name}:{request.provider_model}",
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {
                                        **({"role": "assistant"} if not emitted_role else {}),
                                        "content": text,
                                    },
                                    "finish_reason": None,
                                }
                            ],
                        }
                        emitted_role = True
                        yield f"data: {json.dumps(chunk, separators=(',', ':'))}\n\n"
                        continue
                    if event_type == "error":
                        error = payload.get("error")
                        message = error.get("message") if isinstance(error, dict) else "anthropic stream error"
                        raise RuntimeError(str(message))
                    if event_type == "message_stop":
                        final_chunk = {
                            "id": message_id,
                            "object": "chat.completion.chunk",
                            "model": f"{request.provider_name}:{request.provider_model}",
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {},
                                    "finish_reason": _openai_finish_reason(stop_reason),
                                }
                            ],
                            "usage": {
                                "prompt_tokens": usage.get("input_tokens", 0),
                                "completion_tokens": usage.get("output_tokens", 0),
                                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                            },
                        }
                        yield f"data: {json.dumps(final_chunk, separators=(',', ':'))}\n\n"
                        yield "data: [DONE]\n\n"
                        return
