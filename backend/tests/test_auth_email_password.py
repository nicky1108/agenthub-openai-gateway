from fastapi.testclient import TestClient

from app.main import create_app


def test_email_registration_and_login_sets_session_cookie(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        register_response = client.post(
            "/auth/register",
            json={
                "name": "alice",
                "email": "alice@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        login_response = client.post(
            "/auth/login",
            json={
                "email": "alice@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        me_response = client.get("/auth/me")

    assert register_response.status_code == 201
    assert login_response.status_code == 200
    assert me_response.status_code == 200
    assert login_response.cookies.get("agh_session") is not None
    assert me_response.json()["email"] == "alice@example.com"


def test_admin_email_session_can_access_admin_routes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'auth-admin.db'}")
    monkeypatch.setenv("ADMIN_EMAILS_CSV", "admin@example.com")

    with TestClient(create_app()) as client:
        register_response = client.post(
            "/auth/register",
            json={
                "name": "admin",
                "email": "admin@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        login_response = client.post(
            "/auth/login",
            json={
                "email": "admin@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        admin_response = client.get("/admin/settings/overview")
        me_response = client.get("/auth/me")

    assert register_response.status_code == 201
    assert register_response.json()["is_admin"] is True
    assert login_response.status_code == 200
    assert login_response.json()["is_admin"] is True
    assert admin_response.status_code == 200
    assert me_response.status_code == 200
    assert me_response.json()["is_admin"] is True


def test_named_admin_gate_blocks_non_admin_sessions(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'auth-non-admin.db'}")
    monkeypatch.setenv("ADMIN_EMAILS_CSV", "admin@example.com")

    with TestClient(create_app()) as client:
        register_response = client.post(
            "/auth/register",
            json={
                "name": "member",
                "email": "member@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        login_response = client.post(
            "/auth/login",
            json={
                "email": "member@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        admin_response = client.get("/admin/settings/overview")

    assert register_response.status_code == 201
    assert register_response.json()["is_admin"] is False
    assert login_response.status_code == 200
    assert login_response.json()["is_admin"] is False
    assert admin_response.status_code == 401
    assert admin_response.json()["detail"] == "invalid admin credentials"


def test_named_admin_gate_rejects_shared_secret_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'auth-secret-fallback.db'}")
    monkeypatch.setenv("ADMIN_EMAILS_CSV", "admin@example.com")

    with TestClient(create_app()) as client:
        response = client.get("/admin/settings/overview", headers={"x-admin-secret": "change-me"})

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid admin credentials"


def test_logout_revokes_session_cookie(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        client.post(
            "/auth/register",
            json={
                "name": "alice",
                "email": "alice@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        login_response = client.post(
            "/auth/login",
            json={
                "email": "alice@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        assert login_response.status_code == 200

        logout_response = client.post("/auth/logout")
        me_response = client.get("/auth/me")

    assert logout_response.status_code == 200
    assert logout_response.json() == {"status": "logged_out"}
    assert me_response.status_code == 401
