import pathlib

from fastapi.testclient import TestClient

from app.api import openai as openai_api
from app.main import create_app


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
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "real-cli-response"
