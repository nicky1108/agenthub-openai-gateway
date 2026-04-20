import json
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
    return SimpleNamespace(pricing=None)


async def _fake_settle_inference(*args, **kwargs):
    return None


def test_streaming_chat_returns_sse_chunks(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setattr(openai_api.orchestrator, "_http_adapter", lambda provider: MockHttpAdapter())
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
