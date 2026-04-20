from fastapi.testclient import TestClient

from app.main import create_app


def test_admin_dashboard_summary_returns_platform_metrics(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        response = client.get("/admin/dashboard/summary", headers={"x-admin-secret": "change-me"})

    assert response.status_code == 200
    payload = response.json()
    assert "total_requests" in payload
    assert "active_api_keys" in payload
    assert "error_rate" in payload
    assert "rate_limit_hits" in payload
