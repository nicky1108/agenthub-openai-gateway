from fastapi.testclient import TestClient

from app.main import create_app


def _create_api_key(client: TestClient) -> str:
    account_response = client.post(
        "/admin/accounts",
        json={"name": "test-account"},
        headers={"x-admin-secret": "change-me"},
    )
    account_id = account_response.json()["id"]
    key_response = client.post(
        "/admin/api-keys",
        json={"account_id": account_id, "name": "test-key"},
        headers={"x-admin-secret": "change-me"},
    )
    return key_response.json()["api_key"]


def test_models_endpoint_returns_provider_prefixed_model_ids(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

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

        response = client.get("/v1/models", headers={"authorization": f"Bearer {api_key}"})

    assert response.status_code == 200
    payload = response.json()
    ids = [item["id"] for item in payload["data"]]
    assert "codex:gpt-5-codex" in ids
    assert "codex:codex-mini-latest" in ids


def test_models_endpoint_omits_disabled_providers(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

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
        client.post(
            "/admin/providers",
            json={
                "name": "offline",
                "http_enabled": False,
                "cli_enabled": False,
                "route_policy": "fixed-http",
            },
            headers={"x-admin-secret": "change-me"},
        )

        response = client.get("/v1/models", headers={"authorization": f"Bearer {api_key}"})

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["data"]] == [
        "codex:codex-mini-latest",
        "codex:gpt-5-codex",
        "codex:gpt-5.1-codex",
        "codex:gpt-5.1-codex-max",
        "codex:gpt-5.1-codex-mini",
        "codex:gpt-5.2-codex",
        "codex:gpt-5.3-codex",
    ]


def test_models_endpoint_returns_multiple_gemini_models(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        api_key = _create_api_key(client)
        client.post(
            "/admin/providers",
            json={
                "name": "gemini",
                "http_enabled": False,
                "cli_enabled": True,
                "route_policy": "fixed-cli",
                "cli_command": "/bin/echo",
            },
            headers={"x-admin-secret": "change-me"},
        )

        response = client.get("/v1/models", headers={"authorization": f"Bearer {api_key}"})

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["data"]]
    assert "gemini:gemini-2.5-pro" in ids
    assert "gemini:gemini-2.5-flash" in ids
