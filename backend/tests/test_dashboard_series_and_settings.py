import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app


def seed_dashboard_data(database_path) -> None:
    now = datetime.now(timezone.utc)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            INSERT INTO accounts (name, email, status, credit_balance, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("dashboard-account", "dashboard@example.com", "active", 0, now.isoformat()),
        )
        account_id = connection.execute("SELECT id FROM accounts WHERE email = ?", ("dashboard@example.com",)).fetchone()[0]
        connection.execute(
            """
            INSERT INTO api_keys (
                account_id, name, key_prefix, secret_hash, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (account_id, "dashboard-key", "prefix123", "hash", "active", now.isoformat()),
        )
        api_key_id = connection.execute("SELECT id FROM api_keys WHERE key_prefix = ?", ("prefix123",)).fetchone()[0]
        rows = [
            (account_id, api_key_id, "codex", "codex:gpt-5.4", "success", (now - timedelta(hours=1)).isoformat()),
            (account_id, api_key_id, "codex", "codex:gpt-5.4", "error", (now - timedelta(hours=2)).isoformat()),
            (account_id, api_key_id, "gemini", "gemini:gemini-2.5-flash", "limited", (now - timedelta(days=1)).isoformat()),
        ]
        connection.executemany(
            """
            INSERT INTO usage_records (
                account_id, api_key_id, provider_name, model_id, outcome, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()
    finally:
        connection.close()


def test_dashboard_timeseries_and_settings_overview(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "gateway.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "github-client")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "github-secret")
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://127.0.0.1:3000")

    with TestClient(create_app()) as client:
        assert client.get("/healthz").status_code == 200

    seed_dashboard_data(database_path)

    with TestClient(create_app()) as client:
        series_24h = client.get(
            "/admin/dashboard/timeseries?window=24h",
            headers={"x-admin-secret": "change-me"},
        )
        series_7d = client.get(
            "/admin/dashboard/timeseries?window=7d",
            headers={"x-admin-secret": "change-me"},
        )
        settings_response = client.get(
            "/admin/settings/overview",
            headers={"x-admin-secret": "change-me"},
        )

    assert series_24h.status_code == 200
    series_24h_payload = series_24h.json()
    assert series_24h_payload["window"] == "24h"
    assert len(series_24h_payload["buckets"]) == 24
    assert sum(bucket["total_requests"] for bucket in series_24h_payload["buckets"]) == 2
    assert sum(bucket["error_requests"] for bucket in series_24h_payload["buckets"]) == 1

    assert series_7d.status_code == 200
    series_7d_payload = series_7d.json()
    assert series_7d_payload["window"] == "7d"
    assert len(series_7d_payload["buckets"]) == 7
    assert sum(bucket["total_requests"] for bucket in series_7d_payload["buckets"]) == 3
    assert sum(bucket["limited_requests"] for bucket in series_7d_payload["buckets"]) == 1

    assert settings_response.status_code == 200
    assert settings_response.json() == {
        "gateway_host": "127.0.0.1",
        "gateway_port": 8787,
        "frontend_base_url": "http://127.0.0.1:3000",
        "database_scheme": "sqlite+aiosqlite",
        "email_password_enabled": True,
        "github_oauth_enabled": True,
        "google_oauth_enabled": False,
        "admin_secret_configured": True,
    }
