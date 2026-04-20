import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def test_streaming_chat_returns_sse_chunks(tmp_path, monkeypatch) -> None:
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

        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "codex:default",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
        ) as response:
            body = b"".join(response.iter_bytes()).decode()

    assert response.status_code == 200
    assert "chat.completion.chunk" in body
    assert "[DONE]" in body


def test_streaming_chat_returns_404_for_unknown_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "missing:default",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
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
            },
        ),
        (
            "openai",
            {
                "name": "openai",
                "http_enabled": True,
                "cli_enabled": True,
                "route_policy": "cli-first",
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
    provider_model = 'default"\n\ndata: {"object":"injected"}'
    model = f"{provider_name}:{provider_model}"

    with TestClient(create_app()) as client:
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
        ) as response:
            body = b"".join(response.iter_bytes()).decode()

    assert response.status_code == 200
    data_lines = [line for line in body.splitlines() if line.startswith("data: ")]
    assert data_lines[-1] == "data: [DONE]"

    payloads = [json.loads(line.removeprefix("data: ")) for line in data_lines[:-1]]
    assert len(payloads) == 2
    assert [payload["model"] for payload in payloads] == [model, model]
