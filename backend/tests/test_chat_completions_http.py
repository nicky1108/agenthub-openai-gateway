import pytest
from fastapi.testclient import TestClient
import logging

from types import SimpleNamespace

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
