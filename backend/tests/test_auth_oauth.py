import sqlite3

from fastapi.testclient import TestClient

from app.main import create_app


def test_auth_provider_status_and_disabled_oauth_routes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        provider_status = client.get("/auth/providers")
        github_response = client.get("/auth/oauth/github")
        google_response = client.get("/auth/oauth/google")

    assert provider_status.status_code == 200
    assert provider_status.json() == {
        "email_password_enabled": True,
        "github_enabled": False,
        "google_enabled": False,
    }
    assert github_response.status_code == 503
    assert github_response.json()["detail"] == "github oauth is not configured"
    assert google_response.status_code == 503
    assert google_response.json()["detail"] == "google oauth is not configured"


def test_enabled_github_oauth_redirects_to_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "github-client")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "github-secret")

    with TestClient(create_app()) as client:
        response = client.get("/auth/oauth/github", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert "github.com/login/oauth/authorize" in response.headers["location"]
    assert "client_id=github-client" in response.headers["location"]
    assert "state=" in response.headers["location"]


def test_github_oauth_callback_creates_session(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "gateway.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://127.0.0.1:3000")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "github-client")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "github-secret")

    async def fake_exchange(_: str, __: str) -> dict[str, str]:
        return {"access_token": "github-token"}

    async def fake_profile(_: str) -> dict[str, str]:
        return {
            "subject": "github-user-1",
            "email": "octo@example.com",
            "name": "Octo User",
        }

    monkeypatch.setattr("app.api.auth.exchange_github_code", fake_exchange)
    monkeypatch.setattr("app.api.auth.fetch_github_profile", fake_profile)

    with TestClient(create_app()) as client:
        start = client.get("/auth/oauth/github", follow_redirects=False)
        state = start.cookies.get("agh_oauth_state")
        callback = client.get(
            f"/auth/oauth/github/callback?code=oauth-code&state={state}",
            cookies={"agh_oauth_state": state or "", "agh_oauth_provider": "github"},
            follow_redirects=False,
        )
        me = client.get("/auth/me", cookies=callback.cookies)

    assert callback.status_code in (302, 307)
    assert callback.headers["location"] == "http://127.0.0.1:3000/"
    assert callback.cookies.get("agh_session")
    assert me.status_code == 200
    assert me.json()["email"] == "octo@example.com"

    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            "SELECT oauth_provider, oauth_subject, email FROM accounts WHERE email = ?",
            ("octo@example.com",),
        ).fetchone()
    finally:
        connection.close()

    assert row == ("github", "github-user-1", "octo@example.com")
