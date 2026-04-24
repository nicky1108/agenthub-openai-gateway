import sqlite3

from fastapi.testclient import TestClient

from app.main import create_app


def _create_api_key(client: TestClient) -> str:
    account_response = client.post(
        "/admin/accounts",
        json={"name": "provider-admin-account"},
        headers={"x-admin-secret": "change-me"},
    )
    key_response = client.post(
        "/admin/api-keys",
        json={"account_id": account_response.json()["id"], "name": "provider-admin-key"},
        headers={"x-admin-secret": "change-me"},
    )
    return key_response.json()["api_key"]


def test_admin_can_create_and_list_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        create_response = client.post(
            "/admin/providers",
            json={
                "name": "codex",
                "http_enabled": True,
                "cli_enabled": True,
                "route_policy": "http-first",
                "chat_capable": False,
                "stream_capable": True,
                "http_base_url": "http://provider.invalid",
                "cli_command": "/bin/echo",
            },
            headers={"x-admin-secret": "change-me"},
        )
        list_response = client.get(
            "/admin/providers",
            headers={"x-admin-secret": "change-me"},
        )

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    assert create_response.json()["chat_capable"] is False
    assert create_response.json()["stream_capable"] is True
    payload = list_response.json()
    assert payload[0]["name"] == "codex"
    assert payload[0]["route_policy"] == "http-first"
    assert payload[0]["chat_capable"] is False
    assert payload[0]["stream_capable"] is True


def test_admin_provider_defaults_preserve_capability_flags(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        response = client.post(
            "/admin/providers",
            json={
                "name": "openai",
                "http_enabled": True,
                "cli_enabled": False,
                "route_policy": "fixed-http",
                "http_base_url": "http://provider.invalid",
            },
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 201
    assert response.json()["chat_capable"] is True
    assert response.json()["stream_capable"] is True


def test_admin_rejects_duplicate_provider_names(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        first_response = client.post(
            "/admin/providers",
            json={
                "name": "codex",
                "http_enabled": True,
                "cli_enabled": True,
                "route_policy": "http-first",
                "http_base_url": "http://provider.invalid",
                "cli_command": "/bin/echo",
            },
            headers={"x-admin-secret": "change-me"},
        )
        duplicate_response = client.post(
            "/admin/providers",
            json={
                "name": "codex",
                "http_enabled": False,
                "cli_enabled": True,
                "route_policy": "cli-only",
                "cli_command": "/bin/echo",
            },
            headers={"x-admin-secret": "change-me"},
        )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {"detail": "provider already exists"}


def test_admin_rejects_provider_names_containing_colons(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        response = client.post(
            "/admin/providers",
            json={
                "name": "codex:default",
                "http_enabled": True,
                "cli_enabled": False,
                "route_policy": "fixed-http",
                "http_base_url": "http://provider.invalid",
            },
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 422
    assert "must not contain ':'" in str(response.json())


def test_admin_requires_http_base_url_when_http_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        response = client.post(
            "/admin/providers",
            json={
                "name": "codex",
                "http_enabled": True,
                "cli_enabled": False,
                "route_policy": "fixed-http",
            },
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 422
    assert "http_base_url is required" in str(response.json())


def test_admin_requires_cli_command_when_cli_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        response = client.post(
            "/admin/providers",
            json={
                "name": "gemini",
                "http_enabled": False,
                "cli_enabled": True,
                "route_policy": "fixed-cli",
            },
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 422
    assert "cli_command is required" in str(response.json())


def test_admin_can_list_legacy_provider_rows_after_column_backfill(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "gateway.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")

    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) UNIQUE NOT NULL,
                http_enabled BOOLEAN NOT NULL,
                cli_enabled BOOLEAN NOT NULL,
                route_policy VARCHAR(32) NOT NULL DEFAULT 'http-first'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO providers (name, http_enabled, cli_enabled, route_policy)
            VALUES ('legacy-http', 1, 0, 'fixed-http')
            """
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(create_app()) as client:
        response = client.get(
            "/admin/providers",
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 200
    assert response.json()[0]["name"] == "legacy-http"
    assert response.json()[0]["http_enabled"] is True
    assert response.json()[0]["http_base_url"] is None


def test_admin_lists_discovered_provider_models(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        create_response = client.post(
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
        assert create_response.status_code == 201

        response = client.get(
            "/admin/providers/gemini/models",
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 200
    native_models = [item["native_model"] for item in response.json()]
    assert "gemini-2.5-pro" in native_models
    assert "gemini-2.5-flash" in native_models
    assert "gemini-2.5-flash-lite" in native_models


def test_admin_lists_official_pricing_for_provider_models(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        create_response = client.post(
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
        assert create_response.status_code == 201

        response = client.get(
            "/admin/providers/codex/models",
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 200
    gpt54 = next(item for item in response.json() if item["native_model"] == "gpt-5.4")
    assert gpt54["pricing"] == {
        "provider_name": "codex",
        "native_model": "gpt-5.4",
        "source_kind": "official_snapshot",
        "source_url": "https://openai.com/api/pricing/",
        "source_label": "OpenAI API Pricing",
        "currency": "USD",
        "unit": "1M tokens",
        "input_price": 2.5,
        "cached_input_price": 0.25,
        "output_price": 15.0,
        "input_price_high": 5.0,
        "cached_input_price_high": 0.5,
        "output_price_high": 22.5,
        "high_price_threshold_tokens": 270000,
        "notes": "Standard pricing. Higher short-context price applies above 270k context.",
        "synced_at": gpt54["pricing"]["synced_at"],
    }
    gpt54mini = next(item for item in response.json() if item["native_model"] == "gpt-5.4-mini")
    assert gpt54mini["pricing"]["input_price"] == 0.75
    assert gpt54mini["pricing"]["output_price"] == 4.5
    gpt55 = next(item for item in response.json() if item["native_model"] == "gpt-5.5")
    assert gpt55["pricing"]["input_price"] == 5.0
    assert gpt55["pricing"]["cached_input_price"] == 0.5
    assert gpt55["pricing"]["output_price"] == 30.0
    gpt52 = next(item for item in response.json() if item["native_model"] == "gpt-5.2")
    assert gpt52["pricing"]["input_price"] == 1.75
    assert gpt52["pricing"]["cached_input_price"] == 0.175
    assert gpt52["pricing"]["output_price"] == 14.0


def test_admin_can_override_provider_model_pricing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        create_response = client.post(
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
        assert create_response.status_code == 201

        patch_response = client.patch(
            "/admin/providers/gemini/models/gemini-3.1-pro-preview/pricing",
            json={
                "input_price": 3.5,
                "cached_input_price": 0.35,
                "output_price": 18.0,
                "notes": "Temporary manual override",
            },
            headers={"x-admin-secret": "change-me"},
        )

    assert patch_response.status_code == 200
    assert patch_response.json()["source_kind"] == "manual_override"
    assert patch_response.json()["input_price"] == 3.5
    assert patch_response.json()["notes"] == "Temporary manual override"


def test_admin_can_override_provider_model_exposure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        api_key = _create_api_key(client)
        create_response = client.post(
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
        assert create_response.status_code == 201

        patch_response = client.patch(
            "/admin/providers/codex/models/gpt-5-codex",
            json={
                "enabled": False,
                "exposed_model_id": "codex:primary",
            },
            headers={"x-admin-secret": "change-me"},
        )
        models_response = client.get("/v1/models", headers={"authorization": f"Bearer {api_key}"})

    assert patch_response.status_code == 200
    assert patch_response.json()["enabled"] is False
    assert patch_response.json()["exposed_model_id"] == "codex:primary"
    exposed_ids = [item["id"] for item in models_response.json()["data"]]
    assert "codex:primary" not in exposed_ids
    assert "codex:gpt-5-codex" not in exposed_ids


def test_admin_can_add_manual_provider_model(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        api_key = _create_api_key(client)
        create_response = client.post(
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
        assert create_response.status_code == 201

        add_response = client.post(
            "/admin/providers/codex/models",
            json={
                "native_model": "gpt-5.4-experimental",
                "exposed_model_id": "codex:gpt-5.4-experimental",
                "enabled": True,
            },
            headers={"x-admin-secret": "change-me"},
        )
        models_response = client.get("/v1/models", headers={"authorization": f"Bearer {api_key}"})

    assert add_response.status_code == 201
    assert add_response.json()["source"] == "manual_override"
    assert "codex:gpt-5.4-experimental" in [item["id"] for item in models_response.json()["data"]]
