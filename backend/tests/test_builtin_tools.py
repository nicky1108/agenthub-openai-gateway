import json

import httpx
import pytest

from app.services import builtin_tools


@pytest.mark.asyncio
async def test_web_fetch_rejects_localhost_before_network() -> None:
    async def _transport(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("localhost must be blocked before issuing a request")

    result = await builtin_tools.web_fetch(
        {"url": "http://127.0.0.1:8787/private"},
        transport=httpx.MockTransport(_transport),
    )

    assert result["ok"] is False
    assert result["error"] == "blocked_private_host"


@pytest.mark.asyncio
async def test_web_fetch_extracts_text_from_html() -> None:
    async def _transport(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.com/page"
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><head><script>ignore()</script></head><body><h1>Hello</h1><p>World</p></body></html>",
        )

    result = await builtin_tools.web_fetch(
        {"url": "https://example.com/page"},
        transport=httpx.MockTransport(_transport),
        resolver=lambda _host: ["93.184.216.34"],
    )

    assert result["ok"] is True
    assert result["url"] == "https://example.com/page"
    assert result["status_code"] == 200
    assert result["text"] == "Hello World"
    assert result["truncated"] is False


def test_builtin_tool_request_requires_explicit_web_fetch_declaration() -> None:
    assert not builtin_tools.request_enables_web_fetch({"tools": []})
    assert not builtin_tools.request_enables_web_fetch(
        {"tools": [{"type": "function", "function": {"name": "other_tool"}}]}
    )
    assert builtin_tools.request_enables_web_fetch(
        {"tools": [{"type": "function", "function": {"name": "web_fetch"}}]}
    )


def test_builtin_tool_detects_forced_web_fetch_choice() -> None:
    assert not builtin_tools.tool_choice_forces_web_fetch({"tool_choice": "required", "tools": []})
    assert builtin_tools.tool_choice_forces_web_fetch(
        {
            "tool_choice": "required",
            "tools": [{"type": "function", "function": {"name": "web_fetch"}}],
        }
    )
    assert builtin_tools.tool_choice_forces_web_fetch(
        {"tool_choice": {"type": "function", "function": {"name": "web_fetch"}}}
    )
    assert not builtin_tools.tool_choice_forces_web_fetch(
        {"tool_choice": {"type": "function", "function": {"name": "custom_tool"}}}
    )


def test_builtin_tool_defaults_declared_web_fetch_choice() -> None:
    payload = {
        "tools": [{"type": "function", "function": {"name": "web_fetch"}}],
    }

    assert builtin_tools.with_default_web_fetch_tool_choice(payload) == {
        **payload,
        "tool_choice": {"type": "function", "function": {"name": "web_fetch"}},
    }
    assert builtin_tools.with_default_web_fetch_tool_choice(
        {**payload, "tool_choice": "auto"}
    )["tool_choice"] == "auto"


def test_builtin_tool_synthesizes_weather_fetch_from_user_request() -> None:
    message = builtin_tools.synthesize_web_fetch_assistant_message(
        {
            "messages": [{"role": "user", "content": "联网搜索一下杭州今天的天气和日期"}],
            "tools": [{"type": "function", "function": {"name": "web_fetch"}}],
        }
    )

    assert message is not None
    tool_call = message["tool_calls"][0]
    assert tool_call["id"] == builtin_tools.WEB_FETCH_FALLBACK_TOOL_CALL_ID
    assert json.loads(tool_call["function"]["arguments"]) == {
        "url": "https://wttr.in/%E6%9D%AD%E5%B7%9E?format=j1"
    }


@pytest.mark.asyncio
async def test_execute_builtin_tool_calls_returns_tool_messages(monkeypatch) -> None:
    async def _fake_web_fetch(arguments):
        assert arguments == {"url": "https://example.com/page"}
        return {"ok": True, "url": arguments["url"], "text": "Fetched body"}

    monkeypatch.setattr(builtin_tools, "web_fetch", _fake_web_fetch)
    assistant_message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_fetch_1",
                "type": "function",
                "function": {
                    "name": "web_fetch",
                    "arguments": json.dumps({"url": "https://example.com/page"}),
                },
            }
        ],
    }

    tool_messages = await builtin_tools.execute_builtin_tool_calls(assistant_message)

    assert tool_messages == [
        {
            "role": "tool",
            "tool_call_id": "call_fetch_1",
            "name": "web_fetch",
            "content": json.dumps(
                {"ok": True, "url": "https://example.com/page", "text": "Fetched body"},
                ensure_ascii=False,
            ),
        }
    ]


@pytest.mark.asyncio
async def test_execute_builtin_tool_calls_leaves_mixed_tools_to_client(monkeypatch) -> None:
    async def _unexpected_web_fetch(_arguments):
        raise AssertionError("mixed tool calls must not be partially executed")

    monkeypatch.setattr(builtin_tools, "web_fetch", _unexpected_web_fetch)
    assistant_message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_fetch_1",
                "type": "function",
                "function": {
                    "name": "web_fetch",
                    "arguments": json.dumps({"url": "https://example.com/page"}),
                },
            },
            {
                "id": "call_custom_1",
                "type": "function",
                "function": {
                    "name": "custom_tool",
                    "arguments": "{}",
                },
            },
        ],
    }

    assert await builtin_tools.execute_builtin_tool_calls(assistant_message) == []
