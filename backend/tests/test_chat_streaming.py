import asyncio
import json
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.adapters.cli.base import MockCliAdapter
from app.adapters.http.base import MockHttpAdapter
from app.billing.service import billing_service
from app.api import openai as openai_api
from app.main import create_app


def _create_api_key(client: TestClient) -> str:
    account_response = client.post(
        "/admin/accounts",
        json={"name": "chat-stream-account"},
        headers={"x-admin-secret": "change-me"},
    )
    client.post(
        f"/admin/accounts/{account_response.json()['id']}/credits/adjust",
        json={"credits_delta": 5000, "notes": "test credits"},
        headers={"x-admin-secret": "change-me"},
    )
    key_response = client.post(
        "/admin/api-keys",
        json={"account_id": account_response.json()["id"], "name": "chat-stream-key"},
        headers={"x-admin-secret": "change-me"},
    )
    return key_response.json()["api_key"]


async def _fake_quote_request(*args, **kwargs):
    return SimpleNamespace(pricing=None, estimated_credits_ceiling=0.01)


async def _fake_settle_inference(*args, **kwargs):
    return None


def test_streaming_chat_returns_sse_chunks(tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setattr(openai_api.orchestrator, "_http_adapter", lambda provider: MockHttpAdapter())
    monkeypatch.setattr(billing_service, "quote_request", _fake_quote_request)
    monkeypatch.setattr(billing_service, "settle_inference", _fake_settle_inference)
    caplog.set_level(logging.INFO, logger="agenthub.gateway")

    with TestClient(create_app()) as client:
        api_key = _create_api_key(client)
        client.post(
            "/admin/providers",
            json={
                "name": "codex",
                "http_enabled": True,
                "cli_enabled": False,
                "route_policy": "fixed-http",
                "http_base_url": "http://provider.invalid",
            },
            headers={"x-admin-secret": "change-me"},
        )

        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "codex:default",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
            headers={"authorization": f"Bearer {api_key}"},
        ) as response:
            body = b"".join(response.iter_bytes()).decode()

    assert response.status_code == 200
    assert "chat.completion.chunk" in body
    assert "[DONE]" in body
    assert "gateway.request.start" in caplog.text
    assert "gateway.provider.prepare" in caplog.text
    assert "gateway.billing.quote" in caplog.text
    assert "gateway.stream.first_chunk" in caplog.text
    assert "gateway.request.complete" in caplog.text


def test_streaming_chat_uses_gemini_acp_when_enabled(tmp_path, monkeypatch) -> None:
    class FakeGeminiAcpClient:
        def __init__(self) -> None:
            self.initialize_calls = 0
            self.new_session_calls = 0
            self.prompt_stream_calls = 0

        def is_healthy(self) -> bool:
            return True

        async def initialize(self):
            self.initialize_calls += 1
            return {"protocolVersion": 1}

        async def new_session(self, _cwd):
            self.new_session_calls += 1
            return {"sessionId": "stream-session"}

        async def set_model(self, _session_id, _model_id):
            return {}

        async def prompt_stream(self, _session_id, _prompt):
            self.prompt_stream_calls += 1
            yield SimpleNamespace(
                update={
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "ACP"},
                    }
                },
                result=None,
            )
            yield SimpleNamespace(
                update=None,
                result={
                    "stopReason": "end_turn",
                    "_meta": {"quota": {"token_count": {"input_tokens": 12, "output_tokens": 1}}},
                },
            )

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("GEMINI_ACP_ENABLED", "true")
    monkeypatch.setattr(billing_service, "quote_request", _fake_quote_request)
    monkeypatch.setattr(billing_service, "settle_inference", _fake_settle_inference)
    fake_client = FakeGeminiAcpClient()
    runtime = {
        "client": fake_client,
        "lock": asyncio.Lock(),
        "initialized": False,
        "session_id": None,
        "model_id": None,
        "waiters": 0,
    }
    monkeypatch.setattr(openai_api.orchestrator, "_gemini_acp_runtime", lambda _provider: runtime)

    with TestClient(create_app()) as client:
        api_key = _create_api_key(client)
        client.post(
            "/admin/providers",
            json={
                "name": "gemini",
                "http_enabled": False,
                "cli_enabled": True,
                "route_policy": "fixed-cli",
                "cli_command": "/bin/echo",
            },
            headers={"x-admin-secret": "change-me"},
        )

        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "gemini:gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
            headers={"authorization": f"Bearer {api_key}"},
        ) as response:
            body = b"".join(response.iter_bytes()).decode()

    assert response.status_code == 200
    assert '"content": "ACP"' in body
    assert '"finish_reason": "stop"' in body
    assert "[DONE]" in body
    assert fake_client.prompt_stream_calls == 1


def test_streaming_chat_returns_404_for_unknown_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setattr(billing_service, "quote_request", _fake_quote_request)
    monkeypatch.setattr(billing_service, "settle_inference", _fake_settle_inference)

    with TestClient(create_app()) as client:
        api_key = _create_api_key(client)
        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "missing:default",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
            headers={"authorization": f"Bearer {api_key}"},
        ) as response:
            body = b"".join(response.iter_bytes()).decode()

    assert response.status_code == 404
    assert body == '{"detail":"provider \'missing\' not found"}'


@pytest.mark.parametrize(
    ("provider_name", "provider_payload"),
    [
        (
            "codex",
            {
                "name": "codex",
                "http_enabled": True,
                "cli_enabled": False,
                "route_policy": "fixed-http",
                "http_base_url": "http://provider.invalid",
            },
        ),
        (
            "openai",
            {
                "name": "openai",
                "http_enabled": True,
                "cli_enabled": True,
                "route_policy": "cli-first",
                "http_base_url": "http://provider.invalid",
                "cli_command": "/bin/echo",
            },
        ),
    ],
)
def test_streaming_chat_escapes_model_in_sse_chunks(
    tmp_path,
    monkeypatch,
    provider_name,
    provider_payload,
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setattr(openai_api.orchestrator, "_http_adapter", lambda provider: MockHttpAdapter())
    monkeypatch.setattr(openai_api.orchestrator, "_cli_adapter", lambda provider: MockCliAdapter())
    monkeypatch.setattr(billing_service, "quote_request", _fake_quote_request)
    monkeypatch.setattr(billing_service, "settle_inference", _fake_settle_inference)
    provider_model = 'default"\n\ndata: {"object":"injected"}'
    model = f"{provider_name}:{provider_model}"

    with TestClient(create_app()) as client:
        api_key = _create_api_key(client)
        client.post(
            "/admin/providers",
            json=provider_payload,
            headers={"x-admin-secret": "change-me"},
        )

        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
            headers={"authorization": f"Bearer {api_key}"},
        ) as response:
            body = b"".join(response.iter_bytes()).decode()

    assert response.status_code == 200
    data_lines = [line for line in body.splitlines() if line.startswith("data: ")]
    assert data_lines[-1] == "data: [DONE]"

    payloads = [json.loads(line.removeprefix("data: ")) for line in data_lines[:-1]]
    assert len(payloads) == 2
    assert [payload["model"] for payload in payloads] == [model, model]
