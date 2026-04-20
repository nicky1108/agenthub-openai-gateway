import pathlib

from fastapi.testclient import TestClient

from app.api import openai as openai_api
from app.main import create_app


def _create_api_key(client: TestClient) -> str:
    account_response = client.post(
        "/admin/accounts",
        json={"name": "chat-routing-account"},
        headers={"x-admin-secret": "change-me"},
    )
    key_response = client.post(
        "/admin/api-keys",
        json={"account_id": account_response.json()["id"], "name": "chat-routing-key"},
        headers={"x-admin-secret": "change-me"},
    )
    return key_response.json()["api_key"]


def test_cli_first_route_uses_cli_response(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    fixture = pathlib.Path(__file__).parent / "fixtures" / "echo_chat.py"
    python_executable = pathlib.Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"
    original_http_builder = openai_api.orchestrator._http_adapter
    monkeypatch.setattr(
        openai_api.orchestrator,
        "_http_adapter",
        lambda provider: original_http_builder(provider),
    )

    with TestClient(create_app()) as client:
        api_key = _create_api_key(client)
        create_response = client.post(
            "/admin/providers",
            json={
                "name": "openai",
                "http_enabled": False,
                "cli_enabled": True,
                "route_policy": "cli-first",
                "cli_command": str(python_executable),
                "cli_args_json": f'[\"{fixture}\"]',
            },
            headers={"x-admin-secret": "change-me"},
        )
        assert create_response.status_code == 201

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "openai:default",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "real-cli-response"


def test_gemini_cli_provider_uses_gemini_adapter(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    fixture = pathlib.Path(__file__).parent / "fixtures" / "gemini_stub.py"
    python_executable = pathlib.Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"

    with TestClient(create_app()) as client:
        api_key = _create_api_key(client)
        create_response = client.post(
            "/admin/providers",
            json={
                "name": "gemini",
                "http_enabled": False,
                "cli_enabled": True,
                "route_policy": "fixed-cli",
                "cli_command": str(python_executable),
                "cli_args_json": f'[\"{fixture}\"]',
            },
            headers={"x-admin-secret": "change-me"},
        )
        assert create_response.status_code == 201

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemini:gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "gemini:gemini-2.5-flash:ok"
