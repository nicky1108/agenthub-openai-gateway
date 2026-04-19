from fastapi.testclient import TestClient

from app.main import create_app


def test_cli_first_route_uses_cli_response() -> None:
    client = TestClient(create_app())
    client.post(
        "/admin/providers",
        json={
            "name": "gemini",
            "http_enabled": True,
            "cli_enabled": True,
            "route_policy": "cli-first",
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
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "mocked-cli-response"
