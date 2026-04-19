from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def test_admin_can_create_and_list_provider() -> None:
    database_path = Path("data/gateway.db")
    if database_path.exists():
        database_path.unlink()

    with TestClient(create_app()) as client:
        create_response = client.post(
            "/admin/providers",
            json={
                "name": "codex",
                "http_enabled": True,
                "cli_enabled": True,
                "route_policy": "http-first",
            },
            headers={"x-admin-secret": "change-me"},
        )
        list_response = client.get(
            "/admin/providers",
            headers={"x-admin-secret": "change-me"},
        )

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload[0]["name"] == "codex"
    assert payload[0]["route_policy"] == "http-first"
