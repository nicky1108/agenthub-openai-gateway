import json
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.adapters.base import ChatRequest
from app.adapters.native.gemini import GeminiNativeAdapter, load_gemini_oauth_credentials
from app.core.models import ProviderRecord
from app.orchestration.chat import ChatOrchestrator


def _write_gemini_auth(path: Path, *, expires_delta: int = 3600) -> str:
    token = "ya29.fake-access-token"
    path.write_text(
        json.dumps(
            {
                "access_token": token,
                "refresh_token": "fake-refresh-token",
                "expiry_date": int((time.time() + expires_delta) * 1000),
            }
        ),
        encoding="utf-8",
    )
    return token


def _request(**overrides) -> ChatRequest:
    payload = {
        "provider_name": "gemini",
        "provider_model": "gemini-2.5-flash",
        "messages": [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "hello"},
        ],
        "stream": False,
        "request_id": "req-gemini-native",
        "provider_options": {},
    }
    payload.update(overrides)
    return ChatRequest(**payload)


def test_gemini_oauth_loader_reads_cli_credentials(tmp_path) -> None:
    auth_file = tmp_path / "oauth_creds.json"
    token = _write_gemini_auth(auth_file)

    credentials = load_gemini_oauth_credentials(str(auth_file), refresh_skew_seconds=120)

    assert credentials.access_token == token
    assert credentials.refresh_token == "fake-refresh-token"


@pytest.mark.asyncio
async def test_gemini_native_chat_maps_request_and_stream_response(tmp_path) -> None:
    auth_file = tmp_path / "oauth_creds.json"
    token = _write_gemini_auth(auth_file)
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["accept"] = request.headers.get("accept")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        events = "\n\n".join(
            [
                'data: {"response":{"candidates":[{"content":{"parts":[{"text":"native "}]}}]}}',
                'data: {"response":{"candidates":[{"content":{"parts":[{"text":"ok"}]},"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":5,"candidatesTokenCount":2,"totalTokenCount":7,"cachedContentTokenCount":1}}}',
            ]
        )
        return httpx.Response(200, content=f"{events}\n\n".encode("utf-8"))

    adapter = GeminiNativeAdapter(
        auth_file=str(auth_file),
        project_id="test-project",
        base_url="https://cloudcode-pa.googleapis.com",
        timeout_seconds=5,
        refresh_skew_seconds=120,
        thinking_budget=0,
        transport=httpx.MockTransport(handler),
    )

    result = await adapter.chat(
        _request(
            max_tokens=16,
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
                "tool_choice": "auto",
            },
        )
    )

    body = captured["body"]
    assert captured["url"] == "https://cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"
    assert captured["auth"] == f"Bearer {token}"
    assert captured["accept"] == "text/event-stream"
    assert body["project"] == "test-project"
    assert body["model"] == "gemini-2.5-flash"
    assert body["request"]["systemInstruction"]["parts"][0]["text"] == "Be brief."
    assert body["request"]["contents"] == [{"role": "user", "parts": [{"text": "hello"}]}]
    assert body["request"]["tools"][0]["functionDeclarations"][0]["name"] == "lookup"
    assert body["request"]["toolConfig"]["functionCallingConfig"]["mode"] == "AUTO"
    assert body["request"]["generationConfig"]["maxOutputTokens"] == 16
    assert body["request"]["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 0
    assert result["choices"][0]["message"]["content"] == "native ok"
    assert result["usage"]["prompt_tokens"] == 5
    assert result["usage"]["prompt_tokens_details"]["cached_tokens"] == 1


@pytest.mark.asyncio
async def test_gemini_native_stream_maps_text_delta_and_done(tmp_path) -> None:
    auth_file = tmp_path / "oauth_creds.json"
    _write_gemini_auth(auth_file)

    async def handler(request: httpx.Request) -> httpx.Response:
        events = "\n\n".join(
            [
                'data: {"response":{"candidates":[{"content":{"parts":[{"text":"he"}]}}]}}',
                'data: {"response":{"candidates":[{"content":{"parts":[{"text":"llo"}]},"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":1,"candidatesTokenCount":2,"totalTokenCount":3}}}',
            ]
        )
        return httpx.Response(200, content=f"{events}\n\n".encode("utf-8"))

    adapter = GeminiNativeAdapter(
        auth_file=str(auth_file),
        project_id="test-project",
        refresh_skew_seconds=120,
        transport=httpx.MockTransport(handler),
    )

    chunks = [chunk async for chunk in adapter.stream_chat(_request(stream=True))]

    assert '"content": "he"' in chunks[0]
    assert '"content": "llo"' in chunks[1]
    assert '"finish_reason": "stop"' in chunks[2]
    assert chunks[3] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_orchestrator_prefers_gemini_native_then_falls_back_to_cli(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_NATIVE_ENABLED", "true")
    monkeypatch.setenv("GEMINI_ACP_ENABLED", "false")
    orchestrator = ChatOrchestrator()
    provider = ProviderRecord(name="gemini", cli_enabled=True, route_policy="fixed-cli", cli_command="gemini")
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
    monkeypatch.setattr(orchestrator, "_gemini_native_adapter", lambda: FailingNative())
    monkeypatch.setattr(orchestrator, "_cli_adapter", lambda provider: FallbackCli())

    result = await orchestrator.run({"model": "gemini:gemini-2.5-flash", "messages": []}, SimpleNamespace())

    assert result["choices"][0]["message"]["content"] == "cli fallback"
