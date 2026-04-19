import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def test_chat_completions_returns_openai_shaped_response(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        client.post(
            "/admin/providers",
            json={
                "name": "codex",
                "http_enabled": True,
                "cli_enabled": False,
                "route_policy": "fixed-http",
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
