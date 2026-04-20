from fastapi.testclient import TestClient

from app.main import create_app


def test_models_endpoint_returns_provider_prefixed_model_ids(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
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

        response = client.get("/v1/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["id"] == "codex:default"


def test_models_endpoint_omits_disabled_providers(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
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

        response = client.get("/v1/models")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["data"]] == ["codex:default"]
