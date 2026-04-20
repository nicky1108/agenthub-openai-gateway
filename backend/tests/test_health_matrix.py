import sqlite3

from fastapi.testclient import TestClient

from app.main import create_app


def test_admin_health_matrix_reports_provider_capabilities(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        client.post(
            "/admin/providers",
            json={
                "name": "opencode",
                "http_enabled": False,
                "cli_enabled": True,
                "route_policy": "fixed-cli",
                "chat_capable": False,
                "stream_capable": False,
                "cli_command": "/bin/echo",
            },
            headers={"x-admin-secret": "change-me"},
        )

        response = client.get("/admin/health", headers={"x-admin-secret": "change-me"})

    assert response.status_code == 200
    assert response.json()[0]["name"] == "opencode"
    assert response.json()[0]["capabilities"]["cli"] is True
    assert response.json()[0]["capabilities"]["chat"] is False
    assert response.json()[0]["capabilities"]["stream"] is False


def test_startup_backfills_missing_provider_transport_and_capability_columns(
    tmp_path,
    monkeypatch,
) -> None:
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
            VALUES ('legacy', 1, 0, 'fixed-http')
            """
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(create_app()) as client:
        health_response = client.get("/admin/health", headers={"x-admin-secret": "change-me"})
        create_response = client.post(
            "/admin/providers",
            json={
                "name": "new-http",
                "http_enabled": True,
                "cli_enabled": False,
                "route_policy": "fixed-http",
                "http_base_url": "http://provider.invalid",
                "http_headers_json": "{}",
                "cli_args_json": "[]",
                "cli_env_json": "{}",
            },
            headers={"x-admin-secret": "change-me"},
        )

    assert health_response.status_code == 200
    assert health_response.json() == [
        {
            "name": "legacy",
            "route_policy": "fixed-http",
            "capabilities": {
                "chat": True,
                "stream": True,
                "http": True,
                "cli": False,
            },
        }
    ]
    assert create_response.status_code == 201
    assert create_response.json()["exposed_model"] == "default"
