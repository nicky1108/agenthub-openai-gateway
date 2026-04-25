from __future__ import annotations

import inspect
import ipaddress
import json
import re
import socket
from collections.abc import Callable, Sequence
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

WEB_FETCH_TOOL_NAMES = {"web_fetch", "web-fetch"}
WEB_FETCH_MAX_BYTES = 1_000_000
WEB_FETCH_MAX_CHARS = 20_000
WEB_FETCH_MAX_REDIRECTS = 3
WEB_FETCH_TIMEOUT_SECONDS = 10.0

_TEXT_CONTENT_TYPES = {
    "application/json",
    "application/ld+json",
    "application/rss+xml",
    "application/xhtml+xml",
    "application/xml",
    "application/atom+xml",
}


class WebFetchError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


Resolver = Callable[[str], Sequence[str]]


def _default_resolver(host: str) -> list[str]:
    return sorted(
        {
            str(item[4][0])
            for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            if item and len(item) >= 5
        }
    )


def _normalize_url(raw_url: object) -> str:
    url = str(raw_url or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise WebFetchError("unsupported_url_scheme")
    if not parsed.hostname:
        raise WebFetchError("missing_url_host")
    if parsed.username or parsed.password:
        raise WebFetchError("unsupported_url_credentials")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def _is_blocked_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return True
    return not address.is_global


def _validate_public_host(url: str, resolver: Resolver | None = None) -> None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise WebFetchError("missing_url_host")
    if host == "localhost" or host.endswith(".localhost"):
        raise WebFetchError("blocked_private_host")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        resolve = resolver or _default_resolver
        try:
            addresses = list(resolve(host))
        except OSError as exc:
            raise WebFetchError("dns_resolution_failed") from exc
        if not addresses:
            raise WebFetchError("dns_resolution_failed")
    else:
        addresses = [host]
    if any(_is_blocked_ip(address) for address in addresses):
        raise WebFetchError("blocked_private_host")


def _content_type_is_text(content_type: str) -> bool:
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type.startswith("text/") or media_type in _TEXT_CONTENT_TYPES or media_type.endswith("+json")


async def _read_limited(response: httpx.Response, max_bytes: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    total = 0
    truncated = False
    async for chunk in response.aiter_bytes():
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            remaining = max(max_bytes - sum(len(item) for item in chunks), 0)
            if remaining:
                chunks.append(chunk[:remaining])
            truncated = True
            break
        chunks.append(chunk)
    await response.aclose()
    return b"".join(chunks), truncated


def _decode_response(raw: bytes, response: httpx.Response) -> str:
    encoding = response.encoding or "utf-8"
    try:
        return raw.decode(encoding, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _extract_text(body: str, content_type: str) -> str:
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type in {"text/html", "application/xhtml+xml"}:
        body = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", body)
        body = re.sub(r"(?s)<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", unescape(body)).strip()


async def web_fetch(
    arguments: dict[str, Any],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    resolver: Resolver | None = None,
    timeout_seconds: float = WEB_FETCH_TIMEOUT_SECONDS,
    max_bytes: int = WEB_FETCH_MAX_BYTES,
    max_chars: int = WEB_FETCH_MAX_CHARS,
    max_redirects: int = WEB_FETCH_MAX_REDIRECTS,
) -> dict[str, Any]:
    try:
        url = _normalize_url(arguments.get("url"))
        _validate_public_host(url, resolver)
        headers = {
            "accept": "text/html,application/xhtml+xml,application/json,application/xml,text/plain;q=0.9,*/*;q=0.1",
            "user-agent": "AgentHubGateway-WebFetch/1.0",
        }
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        ) as client:
            for _ in range(max_redirects + 1):
                request = client.build_request("GET", url, headers=headers)
                response = await client.send(request, stream=True)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    await response.aclose()
                    if not location:
                        raise WebFetchError("redirect_missing_location")
                    url = _normalize_url(urljoin(url, location))
                    _validate_public_host(url, resolver)
                    continue
                content_type = response.headers.get("content-type", "")
                if not _content_type_is_text(content_type):
                    await response.aclose()
                    return {
                        "ok": False,
                        "url": url,
                        "status_code": response.status_code,
                        "content_type": content_type,
                        "error": "unsupported_content_type",
                    }
                raw, byte_truncated = await _read_limited(response, max_bytes)
                text = _extract_text(_decode_response(raw, response), content_type)
                char_truncated = len(text) > max_chars
                if char_truncated:
                    text = text[:max_chars]
                return {
                    "ok": True,
                    "url": str(response.url),
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "text": text,
                    "truncated": byte_truncated or char_truncated,
                }
            raise WebFetchError("too_many_redirects")
    except WebFetchError as exc:
        return {"ok": False, "url": str(arguments.get("url") or ""), "error": exc.code}
    except httpx.TimeoutException:
        return {"ok": False, "url": str(arguments.get("url") or ""), "error": "timeout"}
    except httpx.HTTPError as exc:
        return {"ok": False, "url": str(arguments.get("url") or ""), "error": "request_failed", "detail": str(exc)}


def request_enables_web_fetch(payload: dict[str, Any]) -> bool:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return False
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        function = tool.get("function")
        if isinstance(function, dict) and function.get("name") in WEB_FETCH_TOOL_NAMES:
            return True
    return False


def result_assistant_message(result: dict[str, Any]) -> dict[str, Any] | None:
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    choice = choices[0]
    if not isinstance(choice, dict):
        return None
    message = choice.get("message")
    return message if isinstance(message, dict) else None


def _parse_tool_arguments(raw_arguments: object) -> dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if not isinstance(raw_arguments, str) or not raw_arguments.strip():
        return {}
    parsed = json.loads(raw_arguments)
    return parsed if isinstance(parsed, dict) else {}


async def execute_builtin_tool_calls(assistant_message: dict[str, Any]) -> list[dict[str, str]]:
    tool_calls = assistant_message.get("tool_calls")
    if not isinstance(tool_calls, list):
        return []
    executable_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
    tool_messages: list[dict[str, str]] = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            return []
        function = tool_call.get("function")
        if not isinstance(function, dict):
            return []
        tool_name = function.get("name")
        if tool_name not in WEB_FETCH_TOOL_NAMES:
            return []
        executable_calls.append((tool_call, function))

    for tool_call, function in executable_calls:
        try:
            arguments = _parse_tool_arguments(function.get("arguments"))
            maybe_result = web_fetch(arguments)
            result = await maybe_result if inspect.isawaitable(maybe_result) else maybe_result
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            result = {"ok": False, "error": "invalid_tool_arguments", "detail": str(exc)}
        tool_messages.append(
            {
                "role": "tool",
                "tool_call_id": str(tool_call.get("id") or ""),
                "name": "web_fetch",
                "content": json.dumps(result, ensure_ascii=False),
            }
        )
    return tool_messages


def append_tool_exchange(messages: list[dict[str, Any]], assistant_message: dict[str, Any], tool_messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    if not tool_messages:
        return messages
    assistant_tool_message = {
        "role": "assistant",
        "content": assistant_message.get("content") or "",
        "tool_calls": assistant_message.get("tool_calls") or [],
    }
    return [*messages, assistant_tool_message, *tool_messages]
