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
            },
            headers={"x-admin-secret": "change-me"},
        )

        response = client.get("/admin/health", headers={"x-admin-secret": "change-me"})

    assert response.status_code == 200
    assert response.json()[0]["name"] == "opencode"
    assert response.json()[0]["capabilities"]["cli"] is True
