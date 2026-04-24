import json

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
    monkeypatch.setenv("CODEX_MODELS_CACHE_FILE", str(tmp_path / "missing-codex-models.json"))

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
    assert "codex:gpt-5.5" in ids
    assert "codex:gpt-5.4" in ids
    assert "codex:gpt-5.4-mini" in ids
    assert "codex:gpt-5.4-nano" in ids
    assert "codex:gpt-5.2" in ids


def test_models_endpoint_discovers_codex_models_from_local_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    cache_file = tmp_path / "codex-models-cache.json"
    cache_file.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": "gpt-5.5",
                        "display_name": "GPT-5.5",
                        "visibility": "list",
                        "supported_in_api": True,
                    },
                    {
                        "slug": "gpt-5.3-codex-spark",
                        "display_name": "GPT-5.3-Codex-Spark",
                        "visibility": "list",
                        "supported_in_api": False,
                    },
                    {
                        "slug": "codex-auto-review",
                        "display_name": "Codex Auto Review",
                        "visibility": "hide",
                        "supported_in_api": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_MODELS_CACHE_FILE", str(cache_file))

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

    ids = [item["id"] for item in response.json()["data"]]
    assert "codex:gpt-5.5" in ids
    assert "codex:gpt-5.3-codex-spark" not in ids
    assert "codex:codex-auto-review" not in ids


def test_models_endpoint_omits_disabled_providers(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("CODEX_MODELS_CACHE_FILE", str(tmp_path / "missing-codex-models.json"))

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
    ids = [item["id"] for item in payload["data"]]
    assert ids == sorted(ids)
    assert ids == [
        "codex:codex-mini-latest",
        "codex:gpt-5-codex",
        "codex:gpt-5.1-codex",
        "codex:gpt-5.1-codex-max",
        "codex:gpt-5.1-codex-mini",
        "codex:gpt-5.2",
        "codex:gpt-5.2-codex",
        "codex:gpt-5.3-codex",
        "codex:gpt-5.4",
        "codex:gpt-5.4-mini",
        "codex:gpt-5.4-nano",
        "codex:gpt-5.5",
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
    assert "gemini:gemini-2.5-flash-lite" in ids
    assert "gemini:gemini-3.1-pro-preview" in ids
