import sqlite3

from fastapi.testclient import TestClient

from app.main import create_app


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
