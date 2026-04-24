import base64
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx

from app.adapters.base import ChatRequest
from app.runtime.logging import elapsed_ms, log_gateway_event


DEFAULT_CODEX_NATIVE_BASE_URL = "https://chatgpt.com/backend-api/codex"
DEFAULT_CODEX_INSTRUCTIONS = "You are a helpful assistant."


class CodexNativeAuthError(RuntimeError):
    """Raised when local Codex OAuth credentials are missing or unusable."""


class CodexNativeProviderError(RuntimeError):
    """Raised when the Codex backend rejects or fails a native request."""


@dataclass(slots=True)
class CodexOAuthCredentials:
    access_token: str
    account_id: str | None = None


def _base64url_json(segment: str) -> dict[str, Any]:
    padded = segment + "=" * (-len(segment) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    payload = json.loads(raw.decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _jwt_exp(access_token: str) -> int | None:
    parts = access_token.split(".")
    if len(parts) < 2:
        return None
    try:
        exp = _base64url_json(parts[1]).get("exp")
    except Exception:
        return None
    return int(exp) if isinstance(exp, (int, float)) else None


def load_codex_oauth_credentials(
    auth_file: str,
    *,
    refresh_skew_seconds: int,
) -> CodexOAuthCredentials:
    path = Path(auth_file).expanduser()
    if not path.is_file():
        raise CodexNativeAuthError("Codex OAuth auth file is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CodexNativeAuthError("Codex OAuth auth file is invalid") from exc

    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        raise CodexNativeAuthError("Codex OAuth auth file is missing tokens")
    access_token = tokens.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise CodexNativeAuthError("Codex OAuth access token is missing")
    exp = _jwt_exp(access_token)
    if exp is not None and time.time() >= exp - max(0, int(refresh_skew_seconds)):
        raise CodexNativeAuthError("Codex OAuth access token is expired or expiring")

    account_id = tokens.get("account_id")
    if not isinstance(account_id, str) or not account_id.strip():
        account_id = None
    return CodexOAuthCredentials(access_token=access_token.strip(), account_id=account_id)


def _message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def _convert_content_for_responses(content: Any, *, role: str) -> Any:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return _message_text(content)

    converted: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type in {"input_text", "input_image", "input_file"}:
            converted.append(part)
            continue
        if part_type == "text":
            text = _message_text(part.get("text"))
            converted.append({"type": "output_text" if role == "assistant" else "input_text", "text": text})
            continue
        if part_type == "image_url":
            image_url = part.get("image_url")
            if isinstance(image_url, dict):
                url = image_url.get("url")
                detail = image_url.get("detail")
            else:
                url = image_url
                detail = None
            if isinstance(url, str) and url:
                item: dict[str, Any] = {"type": "input_image", "image_url": url}
                if isinstance(detail, str) and detail:
                    item["detail"] = detail
                converted.append(item)
            continue
        text = _message_text(part.get("text"))
        if text:
            converted.append({"type": "input_text", "text": text})
    return converted or ""


def _split_tool_id(raw_id: Any) -> tuple[str | None, str | None]:
    if not isinstance(raw_id, str):
        return None, None
    value = raw_id.strip()
    if not value:
        return None, None
    if "|" in value:
        call_id, item_id = value.split("|", 1)
        return call_id.strip() or None, item_id.strip() or None
    if value.startswith("fc_"):
        return None, value
    return value, None


def _chat_messages_to_responses_input(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    instructions: list[str] = []
    items: list[dict[str, Any]] = []

    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "user"))
        content = message.get("content", "")
        if role in {"system", "developer"}:
            text = _message_text(content).strip()
            if text:
                instructions.append(text)
            continue
        if role in {"user", "assistant"}:
            converted_content = _convert_content_for_responses(content, role=role)
            if converted_content or role == "user":
                items.append({"role": role, "content": converted_content})
            if role == "assistant":
                tool_calls = message.get("tool_calls")
                if isinstance(tool_calls, list):
                    for index, tool_call in enumerate(tool_calls):
                        if not isinstance(tool_call, dict):
                            continue
                        function = tool_call.get("function")
                        if not isinstance(function, dict):
                            continue
                        name = function.get("name")
                        if not isinstance(name, str) or not name.strip():
                            continue
                        arguments = function.get("arguments", "{}")
                        if isinstance(arguments, dict):
                            arguments = json.dumps(arguments, ensure_ascii=False)
                        elif not isinstance(arguments, str):
                            arguments = str(arguments)
                        call_id = tool_call.get("call_id")
                        if not isinstance(call_id, str) or not call_id.strip():
                            call_id, _ = _split_tool_id(tool_call.get("id"))
                        if not isinstance(call_id, str) or not call_id.strip():
                            call_id = f"call_{index}"
                        items.append(
                            {
                                "type": "function_call",
                                "call_id": call_id.strip(),
                                "name": name.strip(),
                                "arguments": arguments.strip() or "{}",
                            }
                        )
            continue
        if role == "tool":
            call_id, _ = _split_tool_id(message.get("tool_call_id"))
            if not call_id:
                continue
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": _message_text(content),
                }
            )

    return "\n\n".join(instructions).strip() or DEFAULT_CODEX_INSTRUCTIONS, items or [{"role": "user", "content": ""}]


def _responses_tools(tools: Any) -> list[dict[str, Any]] | None:
    if not isinstance(tools, list):
        return None
    converted: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") == "function":
            function = tool.get("function")
            if isinstance(function, dict):
                name = function.get("name")
                parameters = function.get("parameters")
                if isinstance(name, str) and name.strip():
                    converted.append(
                        {
                            "type": "function",
                            "name": name.strip(),
                            "description": _message_text(function.get("description")),
                            "parameters": parameters if isinstance(parameters, dict) else {"type": "object", "properties": {}},
                            "strict": bool(function.get("strict", False)),
                        }
                    )
                continue
            name = tool.get("name")
            parameters = tool.get("parameters")
            if isinstance(name, str) and name.strip():
                converted.append(
                    {
                        "type": "function",
                        "name": name.strip(),
                        "description": _message_text(tool.get("description")),
                        "parameters": parameters if isinstance(parameters, dict) else {"type": "object", "properties": {}},
                        "strict": bool(tool.get("strict", False)),
                    }
                )
    return converted or None


def _responses_tool_choice(tool_choice: Any) -> Any:
    if isinstance(tool_choice, str):
        return tool_choice
    if not isinstance(tool_choice, dict):
        return tool_choice
    choice_type = tool_choice.get("type")
    if choice_type == "function":
        function = tool_choice.get("function")
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            return {"type": "function", "name": function["name"]}
    return tool_choice


def _dict_get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _extract_text_from_output_item(item: Any) -> str:
    if _dict_get(item, "type") != "message":
        return ""
    parts = _dict_get(item, "content", [])
    if not isinstance(parts, list):
        return ""
    chunks: list[str] = []
    for part in parts:
        if _dict_get(part, "type") in {"output_text", "text"}:
            text = _dict_get(part, "text", "")
            if isinstance(text, str):
                chunks.append(text)
    return "".join(chunks)


def _tool_call_from_output_item(item: Any) -> dict[str, Any] | None:
    item_type = _dict_get(item, "type")
    if item_type not in {"function_call", "custom_tool_call"}:
        return None
    call_id = _dict_get(item, "call_id") or _dict_get(item, "id") or "call_0"
    name = _dict_get(item, "name", "")
    arguments = _dict_get(item, "arguments")
    if arguments is None:
        arguments = _dict_get(item, "input", "{}")
    if isinstance(arguments, dict):
        arguments = json.dumps(arguments, ensure_ascii=False)
    elif not isinstance(arguments, str):
        arguments = str(arguments)
    return {
        "id": str(call_id),
        "type": "function",
        "function": {"name": str(name), "arguments": arguments},
    }


def _chat_usage_from_responses(usage: Any) -> dict[str, Any] | None:
    if not isinstance(usage, dict):
        return None
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
    input_details = usage.get("input_tokens_details")
    cached_tokens = 0
    if isinstance(input_details, dict):
        cached_tokens = int(input_details.get("cached_tokens") or 0)
    return {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": total_tokens,
        "prompt_tokens_details": {"cached_tokens": cached_tokens},
    }


def _normalize_response_payload(payload: dict[str, Any], request: ChatRequest) -> dict[str, Any]:
    status = str(payload.get("status") or "").lower()
    if status in {"failed", "cancelled"}:
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("code") or status
        else:
            message = error or status
        raise CodexNativeProviderError(str(message))

    output = payload.get("output")
    output_items = output if isinstance(output, list) else []
    text = "".join(_extract_text_from_output_item(item) for item in output_items).strip()
    if not text and isinstance(payload.get("output_text"), str):
        text = str(payload["output_text"]).strip()
    tool_calls = [tool_call for item in output_items if (tool_call := _tool_call_from_output_item(item)) is not None]
    finish_reason = "tool_calls" if tool_calls else ("incomplete" if status in {"queued", "in_progress", "incomplete"} else "stop")

    message: dict[str, Any] = {"role": "assistant", "content": text}
    if tool_calls:
        message["tool_calls"] = tool_calls
    usage = _chat_usage_from_responses(payload.get("usage"))
    return {
        "id": str(payload.get("id") or "codex-native"),
        "object": "chat.completion",
        "model": f"{request.provider_name}:{request.provider_model}",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        **({"usage": usage} if usage is not None else {}),
    }


class CodexNativeAdapter:
    def __init__(
        self,
        *,
        auth_file: str,
        base_url: str = DEFAULT_CODEX_NATIVE_BASE_URL,
        timeout_seconds: float = 120.0,
        refresh_skew_seconds: int = 120,
        reasoning_effort: str | None = "low",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.auth_file = auth_file
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.refresh_skew_seconds = refresh_skew_seconds
        self.reasoning_effort = reasoning_effort
        self.transport = transport

    def _credentials(self) -> CodexOAuthCredentials:
        return load_codex_oauth_credentials(self.auth_file, refresh_skew_seconds=self.refresh_skew_seconds)

    def _headers(self, credentials: CodexOAuthCredentials) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {credentials.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if credentials.account_id:
            headers["ChatGPT-Account-Id"] = credentials.account_id
        return headers

    def _request_body(self, request: ChatRequest, *, stream: bool) -> dict[str, Any]:
        instructions, input_items = _chat_messages_to_responses_input(request.messages)
        body: dict[str, Any] = {
            "model": request.provider_model,
            "instructions": instructions,
            "input": input_items,
            "store": False,
        }
        tools = _responses_tools(request.provider_options.get("tools"))
        if tools:
            body["tools"] = tools
        tool_choice = request.provider_options.get("tool_choice")
        if tool_choice is not None:
            body["tool_choice"] = _responses_tool_choice(tool_choice)
        if "parallel_tool_calls" in request.provider_options:
            body["parallel_tool_calls"] = request.provider_options["parallel_tool_calls"]
        reasoning = request.provider_options.get("reasoning")
        if isinstance(reasoning, dict):
            body["reasoning"] = reasoning
        elif self.reasoning_effort:
            body["reasoning"] = {"effort": self.reasoning_effort}
        if stream:
            body["stream"] = True
        return body

    def _client(self, credentials: CodexOAuthCredentials) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            headers=self._headers(credentials),
            transport=self.transport,
            trust_env=True,
        )

    def _log_native_event(
        self,
        event: str,
        request: ChatRequest,
        *,
        mode: str,
        elapsed_since: float,
    ) -> None:
        log_gateway_event(
            event,
            request_id=request.request_id,
            provider=request.provider_name,
            model=f"{request.provider_name}:{request.provider_model}",
            mode=mode,
            elapsed_ms=elapsed_ms(elapsed_since),
        )

    async def chat(self, request: ChatRequest) -> dict[str, Any]:
        started_at = perf_counter()
        credentials = self._credentials()
        body = self._request_body(request, stream=True)
        response_id = "codex-native"
        text_parts: list[str] = []
        output_items: list[dict[str, Any]] = []
        completed_response: dict[str, Any] | None = None
        first_output_logged = False

        async with self._client(credentials) as client:
            self._log_native_event("gateway.codex_native.request", request, mode="chat", elapsed_since=started_at)
            async with client.stream("POST", f"{self.base_url}/responses", json=body) as response:
                if response.status_code >= 400:
                    error_text = await response.aread()
                    raise CodexNativeProviderError(
                        f"Codex native request failed with status {response.status_code}: {error_text[:200]!r}"
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw_data = line.removeprefix("data:").strip()
                    if not raw_data or raw_data == "[DONE]":
                        continue
                    event = json.loads(raw_data)
                    if not isinstance(event, dict):
                        continue
                    event_type = str(event.get("type") or "")
                    if event_type == "response.created" and isinstance(event.get("response"), dict):
                        response_id = str(event["response"].get("id") or response_id)
                        continue
                    if event_type in {"response.failed", "response.incomplete", "error"}:
                        error = event.get("error")
                        response_payload = event.get("response")
                        if error is None and isinstance(response_payload, dict):
                            error = response_payload.get("error")
                        raise CodexNativeProviderError(str(error or event_type))
                    if event_type == "response.output_text.delta":
                        delta = event.get("delta")
                        if isinstance(delta, str) and delta:
                            if not first_output_logged:
                                self._log_native_event(
                                    "gateway.codex_native.first_output",
                                    request,
                                    mode="chat",
                                    elapsed_since=started_at,
                                )
                                first_output_logged = True
                            text_parts.append(delta)
                        continue
                    if event_type == "response.output_item.done":
                        item = event.get("item")
                        if isinstance(item, dict):
                            output_items.append(item)
                        continue
                    if event_type == "response.completed" and isinstance(event.get("response"), dict):
                        completed_response = event["response"]
                        response_id = str(completed_response.get("id") or response_id)

        if completed_response is None:
            completed_response = {"id": response_id, "status": "completed", "output": []}
        output = completed_response.get("output")
        if isinstance(output, list) and not output:
            if output_items:
                completed_response["output"] = output_items
            elif text_parts:
                completed_response["output"] = [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "".join(text_parts)}],
                    }
                ]
        elif not isinstance(output, list) and text_parts:
            completed_response["output"] = [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "".join(text_parts)}],
                }
            ]
        self._log_native_event("gateway.codex_native.complete", request, mode="chat", elapsed_since=started_at)
        return _normalize_response_payload(completed_response, request)

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[str]:
        started_at = perf_counter()
        credentials = self._credentials()
        body = self._request_body(request, stream=True)
        response_id = "codex-native"
        emitted_content = False
        completed_response: dict[str, Any] | None = None
        output_text_backfill: list[str] = []

        async with self._client(credentials) as client:
            self._log_native_event("gateway.codex_native.request", request, mode="stream", elapsed_since=started_at)
            async with client.stream("POST", f"{self.base_url}/responses", json=body) as response:
                if response.status_code >= 400:
                    error_text = await response.aread()
                    raise CodexNativeProviderError(
                        f"Codex native stream failed with status {response.status_code}: {error_text[:200]!r}"
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw_data = line.removeprefix("data:").strip()
                    if not raw_data or raw_data == "[DONE]":
                        continue
                    event = json.loads(raw_data)
                    if not isinstance(event, dict):
                        continue
                    event_type = str(event.get("type") or "")
                    if event_type == "response.created" and isinstance(event.get("response"), dict):
                        response_id = str(event["response"].get("id") or response_id)
                        continue
                    if event_type in {"response.failed", "response.incomplete", "error"}:
                        error = event.get("error")
                        response_payload = event.get("response")
                        if error is None and isinstance(response_payload, dict):
                            error = response_payload.get("error")
                        raise CodexNativeProviderError(str(error or event_type))
                    if event_type == "response.output_text.delta":
                        delta = event.get("delta")
                        if not isinstance(delta, str) or not delta:
                            continue
                        if not emitted_content:
                            self._log_native_event(
                                "gateway.codex_native.first_output",
                                request,
                                mode="stream",
                                elapsed_since=started_at,
                            )
                        emitted_content = True
                        output_text_backfill.append(delta)
                        chunk = {
                            "id": response_id,
                            "object": "chat.completion.chunk",
                            "model": f"{request.provider_name}:{request.provider_model}",
                            "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                        }
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                        continue
                    if event_type == "response.output_item.done":
                        item = event.get("item")
                        tool_call = _tool_call_from_output_item(item)
                        if tool_call:
                            response_id = str(event.get("response_id") or response_id)
                            chunk = {
                                "id": response_id,
                                "object": "chat.completion.chunk",
                                "model": f"{request.provider_name}:{request.provider_model}",
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"tool_calls": [{"index": 0, **tool_call}]},
                                        "finish_reason": None,
                                    }
                                ],
                            }
                            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                        continue
                    if event_type == "response.completed" and isinstance(event.get("response"), dict):
                        completed_response = event["response"]
                        response_id = str(completed_response.get("id") or response_id)

        if completed_response is not None and not emitted_content:
            normalized = _normalize_response_payload(completed_response, request)
            text = str(normalized["choices"][0]["message"].get("content") or "")
            if text:
                chunk = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "model": f"{request.provider_name}:{request.provider_model}",
                    "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        usage = _chat_usage_from_responses(completed_response.get("usage") if completed_response else None)
        finish_reason = "stop"
        if completed_response:
            normalized = _normalize_response_payload(completed_response, request)
            finish_reason = str(normalized["choices"][0]["finish_reason"])
        finish_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "model": f"{request.provider_name}:{request.provider_model}",
            "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
            **({"usage": usage} if usage is not None else {}),
        }
        self._log_native_event("gateway.codex_native.complete", request, mode="stream", elapsed_since=started_at)
        yield f"data: {json.dumps(finish_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
