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
            },
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 422
    assert "must not contain ':'" in str(response.json())
