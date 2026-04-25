import pytest
from fastapi.testclient import TestClient
import logging
import json

from types import SimpleNamespace

from app.adapters.base import ChatRequest
from app.adapters.http.base import MockHttpAdapter
from app.billing.service import billing_service
from app.api import openai as openai_api
from app.main import create_app


def _create_api_key(client: TestClient) -> str:
    account_response = client.post(
        "/admin/accounts",
        json={"name": "chat-http-account"},
        headers={"x-admin-secret": "change-me"},
    )
    client.post(
        f"/admin/accounts/{account_response.json()['id']}/credits/adjust",
        json={"credits_delta": 5000, "notes": "test credits"},
        headers={"x-admin-secret": "change-me"},
    )
    key_response = client.post(
        "/admin/api-keys",
        json={"account_id": account_response.json()["id"], "name": "chat-http-key"},
        headers={"x-admin-secret": "change-me"},
    )
    return key_response.json()["api_key"]


async def _fake_quote_request(*args, **kwargs):
    return SimpleNamespace(pricing=None, estimated_credits_ceiling=0.01)


async def _fake_settle_inference(*args, **kwargs):
    return None


class _FallbackCliAdapter:
    async def chat(self, request):
        return {
            "id": "fallback-cli",
            "object": "chat.completion",
            "model": f"{request.provider_name}:{request.provider_model}",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "fallback-cli"},
                    "finish_reason": "stop",
                }
            ],
        }


def test_chat_completions_returns_openai_shaped_response(tmp_path, monkeypatch, caplog) -> None:
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

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "codex:default",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "chat.completion"
    assert payload["choices"][0]["message"]["content"] == "mocked-http-response"
    assert "gateway.request.start" in caplog.text
    assert "gateway.provider.prepare" in caplog.text
    assert "gateway.billing.quote" in caplog.text
    assert "gateway.request.complete" in caplog.text
    assert "request_id=" in caplog.text


def test_chat_completions_accepts_bare_exposed_platform_model_id(tmp_path, monkeypatch) -> None:
    captured: dict[str, str] = {}

    class CapturingHttpAdapter:
        async def chat(self, request: ChatRequest) -> dict[str, object]:
            captured["provider_name"] = request.provider_name
            captured["provider_model"] = request.provider_model
            return {
                "id": "chatcmpl-http-1",
                "object": "chat.completion",
                "model": "codex-mini-latest",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "OK"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
            }

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setattr(openai_api.orchestrator, "_http_adapter", lambda provider: CapturingHttpAdapter())
    monkeypatch.setattr(billing_service, "quote_request", _fake_quote_request)
    monkeypatch.setattr(billing_service, "settle_inference", _fake_settle_inference)

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
        client.patch(
            "/admin/providers/codex/models/codex-mini-latest",
            json={"enabled": False},
            headers={"x-admin-secret": "change-me"},
        )
        client.patch(
            "/admin/providers/codex/models/gpt-5.4",
            json={"exposed_model_id": "codex-mini-latest"},
            headers={"x-admin-secret": "change-me"},
        )

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "codex-mini-latest",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "OK"
    assert captured == {"provider_name": "codex", "provider_model": "gpt-5.4"}


def test_chat_completions_executes_explicit_web_fetch_tool_call(tmp_path, monkeypatch) -> None:
    run_payloads: list[dict[str, object]] = []

    class FakeOrchestrator:
        async def prepare(self, payload, _session):
            return (
                ChatRequest(
                    provider_name="codex",
                    provider_model="gpt-5.4-mini",
                    messages=list(payload["messages"]),
                    stream=bool(payload.get("stream", False)),
                    max_tokens=payload.get("max_tokens"),
                ),
                SimpleNamespace(name="codex", route_policy="fixed-cli"),
            )

        async def run(self, payload, _session):
            run_payloads.append(payload)
            if len(run_payloads) == 1:
                return {
                    "id": "chatcmpl-tool",
                    "object": "chat.completion",
                    "model": payload["model"],
                    "choices": [
                        {
                            "index": 0,
                            "message": {
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
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 1},
                }
            return {
                "id": "chatcmpl-final",
                "object": "chat.completion",
                "model": payload["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Fetched: Example body"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 4},
            }

    async def _fake_web_fetch(arguments):
        assert arguments == {"url": "https://example.com/page"}
        return {"ok": True, "url": arguments["url"], "text": "Example body"}

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setattr(openai_api, "orchestrator", FakeOrchestrator())
    monkeypatch.setattr(openai_api.builtin_tools, "web_fetch", _fake_web_fetch)
    monkeypatch.setattr(billing_service, "quote_request", _fake_quote_request)
    monkeypatch.setattr(billing_service, "settle_inference", _fake_settle_inference)

    with TestClient(create_app()) as client:
        api_key = _create_api_key(client)
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "codex-mini-latest",
                "messages": [{"role": "user", "content": "fetch https://example.com/page"}],
                "tools": [{"type": "function", "function": {"name": "web_fetch"}}],
                "tool_choice": {"type": "function", "function": {"name": "web_fetch"}},
                "stream": False,
            },
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Fetched: Example body"
    assert len(run_payloads) == 2
    assert run_payloads[0]["model"] == "codex:gpt-5.4-mini"
    assert run_payloads[1]["tool_choice"] == "none"
    second_messages = run_payloads[1]["messages"]
    assert second_messages[-2]["role"] == "assistant"
    assert second_messages[-2]["tool_calls"][0]["id"] == "call_fetch_1"
    assert second_messages[-1]["role"] == "tool"
    assert second_messages[-1]["tool_call_id"] == "call_fetch_1"
    assert json.loads(second_messages[-1]["content"])["text"] == "Example body"


def test_chat_completions_uses_gemini_acp_when_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("GEMINI_ACP_ENABLED", "true")
    monkeypatch.setattr(billing_service, "quote_request", _fake_quote_request)
    monkeypatch.setattr(billing_service, "settle_inference", _fake_settle_inference)

    async def _fake_gemini_acp_chat(request, provider):
        return {
            "id": "gemini-acp",
            "object": "chat.completion",
            "model": f"{request.provider_name}:{request.provider_model}",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "gemini-acp"},
                    "finish_reason": "stop",
                }
            ],
        }

    monkeypatch.setattr(openai_api.orchestrator, "_gemini_acp_chat", _fake_gemini_acp_chat)

    with TestClient(create_app()) as client:
        api_key = _create_api_key(client)
        client.post(
            "/admin/providers",
            json={
                "name": "gemini",
                "http_enabled": False,
                "cli_enabled": True,
                "route_policy": "fixed-cli",
                "cli_command": "/opt/homebrew/bin/gemini",
            },
            headers={"x-admin-secret": "change-me"},
        )

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemini:default",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "gemini-acp"


def test_chat_completions_falls_back_when_gemini_acp_errors(tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("GEMINI_ACP_ENABLED", "true")
    monkeypatch.setattr(billing_service, "quote_request", _fake_quote_request)
    monkeypatch.setattr(billing_service, "settle_inference", _fake_settle_inference)
    caplog.set_level(logging.INFO, logger="agenthub.gateway")

    async def _failing_gemini_acp_chat(request, provider):
        raise RuntimeError("acp unavailable")

    monkeypatch.setattr(openai_api.orchestrator, "_gemini_acp_chat", _failing_gemini_acp_chat)
    monkeypatch.setattr(openai_api.orchestrator, "_cli_adapter", lambda provider: _FallbackCliAdapter())

    with TestClient(create_app()) as client:
        api_key = _create_api_key(client)
        client.post(
            "/admin/providers",
            json={
                "name": "gemini",
                "http_enabled": False,
                "cli_enabled": True,
                "route_policy": "fixed-cli",
                "cli_command": "/opt/homebrew/bin/gemini",
            },
            headers={"x-admin-secret": "change-me"},
        )

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemini:default",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "fallback-cli"
    assert "gateway.gemini_acp.fallback" in caplog.text


def test_chat_completions_retries_gemini_acp_once_before_fallback(tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("GEMINI_ACP_ENABLED", "true")
    monkeypatch.setattr(billing_service, "quote_request", _fake_quote_request)
    monkeypatch.setattr(billing_service, "settle_inference", _fake_settle_inference)
    caplog.set_level(logging.INFO, logger="agenthub.gateway")
    attempts = 0

    async def _flaky_gemini_acp_chat(request, provider):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient acp failure")
        return {
            "id": "gemini-acp-retry",
            "object": "chat.completion",
            "model": f"{request.provider_name}:{request.provider_model}",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "retried-acp"},
                    "finish_reason": "stop",
                }
            ],
        }

    monkeypatch.setattr(openai_api.orchestrator, "_gemini_acp_chat", _flaky_gemini_acp_chat)

    with TestClient(create_app()) as client:
        api_key = _create_api_key(client)
        client.post(
            "/admin/providers",
            json={
                "name": "gemini",
                "http_enabled": False,
                "cli_enabled": True,
                "route_policy": "fixed-cli",
                "cli_command": "/opt/homebrew/bin/gemini",
            },
            headers={"x-admin-secret": "change-me"},
        )

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemini:default",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "retried-acp"
    assert attempts == 2
    assert "gateway.gemini_acp.retry" in caplog.text
    assert "gateway.gemini_acp.fallback" not in caplog.text


def test_chat_completions_returns_404_for_unknown_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setattr(billing_service, "quote_request", _fake_quote_request)
    monkeypatch.setattr(billing_service, "settle_inference", _fake_settle_inference)

    with TestClient(create_app()) as client:
        api_key = _create_api_key(client)
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "missing:default",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "provider 'missing' not found"}


@pytest.mark.parametrize(
    ("payload", "missing_field"),
    [
        (
            {
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
            "model",
        ),
        (
            {
                "model": "codex:default",
                "stream": False,
            },
            "messages",
        ),
    ],
)
def test_chat_completions_rejects_payload_without_required_fields(
    tmp_path,
    monkeypatch,
    payload,
    missing_field,
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        api_key = _create_api_key(client)
        response = client.post(
            "/v1/chat/completions",
            json=payload,
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert response.status_code == 422
    response_payload = response.json()
    assert response_payload["detail"][0]["loc"] == ["body", missing_field]
