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
