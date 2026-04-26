import base64
import json
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.adapters.base import ChatRequest
from app.adapters.native.codex import CodexNativeAdapter, CodexNativeAuthError, load_codex_oauth_credentials
from app.api.openai import ChatCompletionCreate
from app.core.models import ProviderRecord
from app.orchestration.chat import ChatOrchestrator


def _b64_json(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _fake_token(*, exp_delta: int = 3600) -> str:
    return f"{_b64_json({'alg': 'none'})}.{_b64_json({'exp': int(time.time()) + exp_delta})}.sig"


def _write_codex_auth(path: Path, *, exp_delta: int = 3600) -> str:
    token = _fake_token(exp_delta=exp_delta)
    path.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": token,
                    "refresh_token": "refresh-token",
                    "account_id": "acct_123",
                },
            }
        ),
        encoding="utf-8",
    )
    return token


def _request(**overrides) -> ChatRequest:
    payload = {
        "provider_name": "codex",
        "provider_model": "gpt-5.4-mini",
        "messages": [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "hello"},
        ],
        "stream": False,
        "request_id": "req-native",
        "provider_options": {},
    }
    payload.update(overrides)
    return ChatRequest(**payload)


def test_chat_completion_create_preserves_tools_extra_fields() -> None:
    payload = ChatCompletionCreate(
        model="codex:gpt-5.4-mini",
        messages=[{"role": "user", "content": "hello"}],
        tools=[{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}],
        tool_choice={"type": "function", "function": {"name": "lookup"}},
    )

    dumped = payload.model_dump()

    assert dumped["tools"][0]["function"]["name"] == "lookup"
    assert dumped["tool_choice"]["function"]["name"] == "lookup"


def test_codex_oauth_loader_rejects_expiring_token(tmp_path) -> None:
    auth_file = tmp_path / "auth.json"
    _write_codex_auth(auth_file, exp_delta=-10)

    with pytest.raises(CodexNativeAuthError):
        load_codex_oauth_credentials(str(auth_file), refresh_skew_seconds=120)


@pytest.mark.asyncio
async def test_codex_native_chat_maps_request_and_response(tmp_path) -> None:
    auth_file = tmp_path / "auth.json"
    token = _write_codex_auth(auth_file)
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["account"] = request.headers.get("chatgpt-account-id")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        events = "\n\n".join(
            [
                'data: {"type":"response.created","response":{"id":"resp_1"}}',
                'data: {"type":"response.output_text.delta","delta":"native ok"}',
                'data: {"type":"response.completed","response":{"id":"resp_1","status":"completed","output":[],"usage":{"input_tokens":10,"output_tokens":3,"total_tokens":13,"input_tokens_details":{"cached_tokens":4}}}}',
            ]
        )
        return httpx.Response(200, content=f"{events}\n\n".encode("utf-8"))

    adapter = CodexNativeAdapter(
        auth_file=str(auth_file),
        base_url="https://chatgpt.com/backend-api/codex",
        timeout_seconds=5,
        refresh_skew_seconds=120,
        reasoning_effort="low",
        transport=httpx.MockTransport(handler),
    )

    result = await adapter.chat(
        _request(
            provider_options={
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "lookup",
                            "description": "Lookup data",
                            "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
                        },
                    }
                ],
                "tool_choice": {"type": "function", "function": {"name": "lookup"}},
                "parallel_tool_calls": False,
            },
        )
    )

    body = captured["body"]
    assert captured["url"] == "https://chatgpt.com/backend-api/codex/responses"
    assert captured["auth"] == f"Bearer {token}"
    assert captured["account"] == "acct_123"
    assert body["model"] == "gpt-5.4-mini"
    assert body["stream"] is True
    assert body["instructions"] == "Be brief."
    assert body["input"] == [{"role": "user", "content": "hello"}]
    assert body["tools"][0]["name"] == "lookup"
    assert body["tool_choice"] == {"type": "function", "name": "lookup"}
    assert body["parallel_tool_calls"] is False
    assert body["reasoning"] == {"effort": "low"}
    assert "max_output_tokens" not in body
    assert result["choices"][0]["message"]["content"] == "native ok"
    assert result["usage"]["prompt_tokens_details"]["cached_tokens"] == 4


@pytest.mark.asyncio
async def test_codex_native_chat_maps_tool_calls(tmp_path) -> None:
    auth_file = tmp_path / "auth.json"
    _write_codex_auth(auth_file)

    async def handler(request: httpx.Request) -> httpx.Response:
        events = "\n\n".join(
            [
                'data: {"type":"response.created","response":{"id":"resp_tool"}}',
                'data: {"type":"response.output_item.done","item":{"type":"function_call","call_id":"call_1","name":"lookup","arguments":"{\\"q\\":\\"hello\\"}"}}',
                'data: {"type":"response.completed","response":{"id":"resp_tool","status":"completed","output":[]}}',
            ]
        )
        return httpx.Response(200, content=f"{events}\n\n".encode("utf-8"))

    adapter = CodexNativeAdapter(
        auth_file=str(auth_file),
        refresh_skew_seconds=120,
        transport=httpx.MockTransport(handler),
    )

    result = await adapter.chat(_request())

    choice = result["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["tool_calls"][0]["function"]["name"] == "lookup"


@pytest.mark.asyncio
async def test_codex_native_stream_maps_text_delta_and_done(tmp_path) -> None:
    auth_file = tmp_path / "auth.json"
    _write_codex_auth(auth_file)
    stream_body = "\n\n".join(
        [
            'data: {"type":"response.created","response":{"id":"resp_stream"}}',
            'data: {"type":"response.output_text.delta","delta":"he"}',
            'data: {"type":"response.output_text.delta","delta":"llo"}',
            'data: {"type":"response.completed","response":{"id":"resp_stream","status":"completed","usage":{"input_tokens":1,"output_tokens":2,"total_tokens":3},"output":[]}}',
        ]
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=f"{stream_body}\n\n".encode("utf-8"))

    adapter = CodexNativeAdapter(
        auth_file=str(auth_file),
        refresh_skew_seconds=120,
        transport=httpx.MockTransport(handler),
    )

    chunks = [chunk async for chunk in adapter.stream_chat(_request(stream=True))]

    assert '"content": "he"' in chunks[0]
    assert '"content": "llo"' in chunks[1]
    assert '"finish_reason": "stop"' in chunks[2]
    assert '"prompt_tokens": 1' in chunks[2]
    assert chunks[3] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_orchestrator_prefers_codex_native_then_falls_back_to_cli(monkeypatch) -> None:
    orchestrator = ChatOrchestrator()
    provider = ProviderRecord(name="codex", cli_enabled=True, route_policy="fixed-cli", cli_command="codex")
    request = _request()

    async def fake_prepare(payload, session):
        return request, provider

    class FailingNative:
        async def chat(self, request):
            raise RuntimeError("native unavailable")

    class FallbackCli:
        async def chat(self, request):
            return {
                "id": "fallback",
                "object": "chat.completion",
                "model": f"{request.provider_name}:{request.provider_model}",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "cli fallback"},
                        "finish_reason": "stop",
                    }
                ],
            }

    monkeypatch.setattr(orchestrator, "prepare", fake_prepare)
    monkeypatch.setattr(orchestrator, "_codex_native_adapter", lambda: FailingNative())
    monkeypatch.setattr(orchestrator, "_cli_adapter", lambda provider: FallbackCli())

    result = await orchestrator.run({"model": "codex:gpt-5.4-mini", "messages": []}, SimpleNamespace())

    assert result["choices"][0]["message"]["content"] == "cli fallback"


@pytest.mark.asyncio
async def test_orchestrator_reports_codex_native_and_cli_failure(monkeypatch) -> None:
    orchestrator = ChatOrchestrator()
    provider = ProviderRecord(name="codex", cli_enabled=True, route_policy="fixed-cli", cli_command="codex")
    request = _request()

    async def fake_prepare(payload, session):
        return request, provider

    class FailingNative:
        async def chat(self, request):
            raise RuntimeError("Codex OAuth auth file is missing")

    class FailingCli:
        async def chat(self, request):
            raise RuntimeError("codex cli failed with exit code 1: not authenticated")

    monkeypatch.setattr(orchestrator, "prepare", fake_prepare)
    monkeypatch.setattr(orchestrator, "_codex_native_adapter", lambda: FailingNative())
    monkeypatch.setattr(orchestrator, "_cli_adapter", lambda provider: FailingCli())

    with pytest.raises(
        RuntimeError,
        match=(
            "codex native failed: Codex OAuth auth file is missing; "
            "codex cli fallback failed: codex cli failed with exit code 1: not authenticated"
        ),
    ):
        await orchestrator.run({"model": "codex:gpt-5.4-mini", "messages": []}, SimpleNamespace())
