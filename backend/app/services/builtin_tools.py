from __future__ import annotations

import inspect
import ipaddress
import json
import re
import socket
from collections.abc import Callable, Sequence
from html import unescape
from typing import Any
from urllib.parse import quote, quote_plus, urljoin, urlsplit, urlunsplit

import httpx

WEB_FETCH_TOOL_NAMES = {"web_fetch", "web-fetch"}
WEB_FETCH_MAX_BYTES = 1_000_000
WEB_FETCH_MAX_CHARS = 20_000
WEB_FETCH_MAX_REDIRECTS = 3
WEB_FETCH_TIMEOUT_SECONDS = 10.0
WEB_FETCH_FALLBACK_TOOL_CALL_ID = "call_web_fetch_gateway_1"
_URL_PATTERN = re.compile(r"https?://[^\s<>'\"）)\]}]+")
_WEB_FETCH_UNAVAILABLE_PATTERNS = (
    "无法联网",
    "不能联网",
    "无法直接联网",
    "无法实时联网",
    "无法获取实时",
    "无法查询实时",
    "没法实时联网",
    "can't browse",
    "cannot browse",
    "unable to browse",
    "can't access the internet",
    "cannot access the internet",
    "unable to access the internet",
)

_TEXT_CONTENT_TYPES = {
    "application/json",
    "application/ld+json",
    "application/rss+xml",
    "application/xhtml+xml",
    "application/xml",
    "application/atom+xml",
    "application/text",
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


def _content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if isinstance(part, dict):
            value = part.get("text") or part.get("content")
            if isinstance(value, str):
                parts.append(value)
        elif isinstance(part, str):
            parts.append(part)
    return " ".join(parts)


def _latest_user_text(messages: object) -> str:
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            return _content_to_text(message.get("content")).strip()
    return ""


def _first_public_url(text: str) -> str | None:
    match = _URL_PATTERN.search(text)
    if not match:
        return None
    return match.group(0).rstrip(".,，。?？!！")


def _weather_url(text: str) -> str | None:
    lower_text = text.lower()
    if "天气" not in text and "weather" not in lower_text and "forecast" not in lower_text:
        return None
    location = ""
    if "天气" in text:
        before_weather = text.split("天气", 1)[0]
        for marker in ("搜索一下", "搜一下", "查询一下", "查一下", "搜索", "查询", "查看", "看一下", "帮我", "请", "联网"):
            if marker in before_weather:
                before_weather = before_weather.rsplit(marker, 1)[-1]
        location = re.sub(r"(今天|今日|现在|实时|当地|日期|和|的|一下)", "", before_weather).strip(" \t\r\n，,。?？")
    if not location:
        match = re.search(r"(?:weather|forecast)(?:\s+(?:in|for))?\s+([A-Za-z][A-Za-z\s.\-]{1,60})", text, re.I)
        if match:
            location = match.group(1).strip(" .,-")
    if not location:
        return None
    return f"https://wttr.in/{quote(location, safe='')}?format=j1"


def _fallback_web_fetch_url(payload: dict[str, Any]) -> str | None:
    text = _latest_user_text(payload.get("messages"))
    if not text:
        return None
    explicit_url = _first_public_url(text)
    if explicit_url is not None:
        return explicit_url
    weather_url = _weather_url(text)
    if weather_url is not None:
        return weather_url
    return f"https://www.bing.com/search?format=rss&q={quote_plus(text[:200])}"


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
    return web_fetch_tool_name(payload) is not None


def web_fetch_tool_name(payload: dict[str, Any]) -> str | None:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return None
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        function = tool.get("function")
        if isinstance(function, dict) and function.get("name") in WEB_FETCH_TOOL_NAMES:
            return str(function["name"])
    return None


def with_default_web_fetch_tool_choice(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("tool_choice") is not None:
        return payload
    tool_name = web_fetch_tool_name(payload)
    if tool_name is None:
        return payload
    return {**payload, "tool_choice": {"type": "function", "function": {"name": tool_name}}}


def synthesize_web_fetch_assistant_message(payload: dict[str, Any]) -> dict[str, Any] | None:
    tool_name = web_fetch_tool_name(payload)
    if tool_name is None:
        return None
    url = _fallback_web_fetch_url(payload)
    if url is None:
        return None
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": WEB_FETCH_FALLBACK_TOOL_CALL_ID,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps({"url": url}, ensure_ascii=False),
                },
            }
        ],
    }


def tool_messages_to_context_message(tool_messages: list[dict[str, str]]) -> dict[str, str]:
    sections = [
        "Web fetch result from the gateway-executed web_fetch tool.",
        "Use this fetched content to answer the user's previous request. Do not claim that browsing is unavailable.",
    ]
    for index, message in enumerate(tool_messages, start=1):
        raw_content = message.get("content", "")
        try:
            payload = json.loads(raw_content)
        except json.JSONDecodeError:
            payload = {"ok": False, "error": "invalid_tool_result", "text": raw_content}
        if not isinstance(payload, dict):
            payload = {"ok": False, "error": "invalid_tool_result", "text": str(payload)}
        url = payload.get("url") or ""
        if payload.get("ok") is True:
            text = str(payload.get("text") or "")
            truncated = " truncated" if payload.get("truncated") else ""
            sections.append(f"[{index}] URL: {url}\nStatus: fetched{truncated}\nContent:\n{text}")
        else:
            error = payload.get("error") or "unknown_error"
            detail = payload.get("detail") or ""
            sections.append(f"[{index}] URL: {url}\nStatus: failed\nError: {error}\nDetail: {detail}")
    return {"role": "user", "content": "\n\n".join(sections)}


def _tool_message_payloads(tool_messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for message in tool_messages:
        raw_content = message.get("content", "")
        try:
            payload = json.loads(raw_content)
        except json.JSONDecodeError:
            payload = {"ok": False, "error": "invalid_tool_result", "text": raw_content}
        if isinstance(payload, dict):
            payloads.append(payload)
        else:
            payloads.append({"ok": False, "error": "invalid_tool_result", "text": str(payload)})
    return payloads


def _nested_value(value: Any, *path: str) -> str:
    current = value
    for key in path:
        if isinstance(current, list):
            current = current[0] if current else None
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    if isinstance(current, list):
        current = current[0] if current else None
    if isinstance(current, dict):
        nested = current.get("value")
        return str(nested) if nested is not None else ""
    return str(current) if current is not None else ""


def _wttr_answer(payload: dict[str, Any]) -> str | None:
    text = str(payload.get("text") or "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    current = data.get("current_condition")
    current_condition = current[0] if isinstance(current, list) and current and isinstance(current[0], dict) else {}
    nearest = data.get("nearest_area")
    nearest_area = nearest[0] if isinstance(nearest, list) and nearest and isinstance(nearest[0], dict) else {}
    if not current_condition:
        return None

    location = _nested_value(nearest_area, "areaName") or "查询地点"
    observation_time = str(current_condition.get("localObsDateTime") or "").strip()
    date = observation_time.split(" ", 1)[0] if observation_time else ""
    weather = _nested_value(current_condition, "weatherDesc") or "未知"
    temp_c = str(current_condition.get("temp_C") or "")
    feels_like_c = str(current_condition.get("FeelsLikeC") or "")
    humidity = str(current_condition.get("humidity") or "")
    wind_kmph = str(current_condition.get("windspeedKmph") or "")

    details: list[str] = []
    if date:
        details.append(f"日期：{date}")
    details.append(f"地点：{location}")
    details.append(f"天气：{weather}")
    if temp_c:
        details.append(f"气温：{temp_c}°C")
    if feels_like_c:
        details.append(f"体感：{feels_like_c}°C")
    if humidity:
        details.append(f"湿度：{humidity}%")
    if wind_kmph:
        details.append(f"风速：{wind_kmph} km/h")
    if observation_time:
        details.append(f"观测时间：{observation_time}")
    return "根据 web_fetch 获取到的实时天气数据：\n" + "\n".join(f"- {detail}" for detail in details)


def direct_answer_from_tool_messages(tool_messages: list[dict[str, str]]) -> str | None:
    payloads = _tool_message_payloads(tool_messages)
    for payload in payloads:
        if payload.get("ok") is not True:
            continue
        wttr_answer = _wttr_answer(payload)
        if wttr_answer is not None:
            return wttr_answer
        url = str(payload.get("url") or "")
        text = str(payload.get("text") or "").strip()
        if text:
            excerpt = text[:4000]
            suffix = "\n\n（内容较长，已截断。）" if len(text) > len(excerpt) else ""
            return f"web_fetch 已成功获取 {url} 的内容：\n\n{excerpt}{suffix}"
    errors = [
        f"{payload.get('url') or ''}: {payload.get('error') or 'unknown_error'}"
        for payload in payloads
        if payload.get("ok") is not True
    ]
    if errors:
        return "web_fetch 执行失败：\n" + "\n".join(f"- {error}" for error in errors)
    return None


def result_claims_web_fetch_unavailable(result: dict[str, Any]) -> bool:
    message = result_assistant_message(result)
    if message is None:
        return False
    content = str(message.get("content") or "").lower()
    return any(pattern in content for pattern in _WEB_FETCH_UNAVAILABLE_PATTERNS)


def replace_result_content(result: dict[str, Any], content: str) -> dict[str, Any]:
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        return result
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return result
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return result
    patched_message = {**message, "content": content}
    patched_choice = {
        **first_choice,
        "message": patched_message,
        "finish_reason": first_choice.get("finish_reason") or "stop",
    }
    return {**result, "choices": [patched_choice, *choices[1:]]}


def tool_choice_forces_web_fetch(payload: dict[str, Any]) -> bool:
    tool_choice = payload.get("tool_choice")
    if tool_choice == "required":
        return request_enables_web_fetch(payload)
    if not isinstance(tool_choice, dict):
        return False
    function = tool_choice.get("function")
    return (
        tool_choice.get("type") == "function"
        and isinstance(function, dict)
        and function.get("name") in WEB_FETCH_TOOL_NAMES
    )


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
