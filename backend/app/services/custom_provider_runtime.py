from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any, Mapping

import httpx

from app.adapters.base import ChatRequest
from app.adapters.http.anthropic_messages import AnthropicMessagesAdapter
from app.adapters.http.openai_compatible import OpenAICompatibleHttpAdapter
from app.core.secrets import reveal_secret
from app.core.settings import Settings
from app.services.provider_guardrails import ensure_safe_provider_url


class CustomProviderRuntimeError(RuntimeError):
    pass


class CustomProviderRequestError(CustomProviderRuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, detail: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class CustomProviderResponseError(CustomProviderRuntimeError):
    pass


_THINK_BLOCK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)


def _provider_value(provider: Mapping[str, Any] | Any, field_name: str) -> str:
    if isinstance(provider, Mapping):
        value = provider.get(field_name)
    else:
        value = getattr(provider, field_name, None)
    if not isinstance(value, str) or not value:
        raise ValueError(f"provider is missing required field '{field_name}'")
    return value


def _provider_protocol(provider: Mapping[str, Any] | Any) -> str:
    if isinstance(provider, Mapping):
        value = provider.get("protocol")
    else:
        value = getattr(provider, "protocol", None)
    return value if isinstance(value, str) and value else "openai"


def _provider_slug(provider: Mapping[str, Any] | Any) -> str | None:
    if isinstance(provider, Mapping):
        value = provider.get("slug")
    else:
        value = getattr(provider, "slug", None)
    return value if isinstance(value, str) and value else None


def _provider_request_payload(request_payload: dict[str, Any], provider_slug: str | None) -> dict[str, Any]:
    model_id = request_payload.get("model")
    if not isinstance(model_id, str) or not model_id:
        raise ValueError("request payload must include a model")
    provider_model = model_id
    if provider_slug and model_id.startswith(f"{provider_slug}:"):
        provider_model = model_id.split(":", 1)[1]
    elif ":" in model_id:
        provider_model = model_id.split(":", 1)[1]

    payload = dict(request_payload)
    payload["model"] = provider_model
    return payload


def _custom_chat_request(request_payload: dict[str, Any], provider_slug: str | None) -> ChatRequest:
    normalized_payload = _provider_request_payload(request_payload, provider_slug)
    passthrough = {
        key: value
        for key, value in request_payload.items()
        if key not in {"model", "messages", "stream", "temperature", "top_p", "max_tokens", "stop", "_request_id"}
    }
    provider_model = str(normalized_payload["model"])
    provider_name = provider_slug or str(request_payload["model"]).split(":", 1)[0]
    return ChatRequest(
        provider_name=provider_name,
        provider_model=provider_model,
        messages=list(request_payload["messages"]),
        stream=bool(request_payload.get("stream", False)),
        request_id=str(request_payload["_request_id"]) if request_payload.get("_request_id") else None,
        temperature=request_payload.get("temperature"),
        top_p=request_payload.get("top_p"),
        max_tokens=request_payload.get("max_tokens"),
        stop=request_payload.get("stop"),
        provider_options=passthrough,
    )


def _custom_http_adapter(
    provider: Mapping[str, Any] | Any,
    *,
    transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
):
    settings = Settings()
    provider_base_url = ensure_safe_provider_url(
        _provider_value(provider, "base_url"),
        strict_dns=settings.require_provider_dns_resolution,
    )
    provider_secret = reveal_secret(_provider_value(provider, "secret_value"))
    if not provider_secret:
        raise ValueError("provider is missing required field 'secret_value'")
    protocol = _provider_protocol(provider)
    if protocol == "anthropic":
        return AnthropicMessagesAdapter(
            base_url=provider_base_url,
            api_key=provider_secret,
            headers={},
            transport=transport,
        )
    return OpenAICompatibleHttpAdapter(
        base_url=provider_base_url,
        api_key=provider_secret,
        headers={},
        transport=transport,
    )


def _validate_provider_response(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("object") != "chat.completion":
        raise CustomProviderResponseError("custom provider returned invalid response")
    if not isinstance(payload.get("choices"), list):
        raise CustomProviderResponseError("custom provider returned invalid response")
    return payload


def strip_thinking_blocks(text: str) -> str:
    return _THINK_BLOCK_PATTERN.sub("", text).lstrip()


def sanitize_completion_payload(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices")
    if not isinstance(choices, list):
        return payload
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            message["content"] = strip_thinking_blocks(content)
    return payload


def summarize_provider_error_response(response: httpx.Response) -> str | None:
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str) and detail:
                return detail
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str) and message:
                    return message

    body_text = response.text.strip()
    if body_text:
        return re.sub(r"\s+", " ", body_text)[:240]
    return None


async def execute_custom_completion(
    request_payload: dict[str, Any],
    provider: Mapping[str, Any] | Any,
    *,
    provider_transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    try:
        adapter = _custom_http_adapter(provider, transport=provider_transport)
        payload = await adapter.chat(_custom_chat_request(request_payload, _provider_slug(provider)))
    except ValueError as exc:
        raise CustomProviderRequestError(str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise CustomProviderRequestError(
            "custom provider request failed",
            status_code=exc.response.status_code,
            detail=summarize_provider_error_response(exc.response),
        ) from exc
    except httpx.HTTPError as exc:
        raise CustomProviderRequestError("custom provider request failed") from exc
    return sanitize_completion_payload(_validate_provider_response(payload))


async def stream_custom_completion(
    request_payload: dict[str, Any],
    provider: Mapping[str, Any] | Any,
    *,
    provider_transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
) -> AsyncIterator[str]:
    try:
        adapter = _custom_http_adapter(provider, transport=provider_transport)
        async for chunk in adapter.stream_chat(_custom_chat_request(request_payload, _provider_slug(provider))):
            yield chunk
    except ValueError as exc:
        raise CustomProviderRequestError(str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise CustomProviderRequestError(
            "custom provider request failed",
            status_code=exc.response.status_code,
            detail=summarize_provider_error_response(exc.response),
        ) from exc
    except httpx.HTTPError as exc:
        raise CustomProviderRequestError("custom provider request failed") from exc
