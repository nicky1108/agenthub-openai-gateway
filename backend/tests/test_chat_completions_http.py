import pytest
from fastapi.testclient import TestClient

from app.adapters.http.base import MockHttpAdapter
from app.api import openai as openai_api
from app.main import create_app


def test_chat_completions_returns_openai_shaped_response(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setattr(openai_api.orchestrator, "_http_adapter", lambda provider: MockHttpAdapter())

    with TestClient(create_app()) as client:
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
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "chat.completion"
    assert payload["choices"][0]["message"]["content"] == "mocked-http-response"


def test_chat_completions_returns_404_for_unknown_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "missing:default",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
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
        response = client.post(
            "/v1/chat/completions",
            json=payload,
        )

    assert response.status_code == 422
    response_payload = response.json()
    assert response_payload["detail"][0]["loc"] == ["body", missing_field]
