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

    assert register_response.status_code == 201
    assert login_response.status_code == 200
    assert login_response.cookies.get("agh_session") is not None


def test_registration_rejects_invalid_email(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        response = client.post(
            "/auth/register",
            json={
                "name": "alice",
                "email": "not-an-email",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )

    assert response.status_code == 422
