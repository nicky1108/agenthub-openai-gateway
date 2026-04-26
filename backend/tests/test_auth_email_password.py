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


def test_admin_can_manage_account_permissions(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'auth-admin-permissions.db'}")
    monkeypatch.setenv("ADMIN_EMAILS_CSV", "admin@example.com")

    with TestClient(create_app()) as client:
        admin_register = client.post(
            "/auth/register",
            json={
                "name": "admin",
                "email": "admin@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        member_register = client.post(
            "/auth/register",
            json={
                "name": "member",
                "email": "member@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        admin_login = client.post(
            "/auth/login",
            json={
                "email": "admin@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        accounts_response = client.get("/admin/accounts")
        member_id = next(row["id"] for row in accounts_response.json() if row["email"] == "member@example.com")
        grant_response = client.patch(f"/admin/accounts/{member_id}", json={"is_admin": True})

    assert admin_register.status_code == 201
    assert member_register.status_code == 201
    assert admin_login.status_code == 200
    assert accounts_response.status_code == 200
    assert any(row["email"] == "admin@example.com" and row["is_admin"] is True for row in accounts_response.json())
    assert any(row["email"] == "member@example.com" and row["is_admin"] is False for row in accounts_response.json())
    assert grant_response.status_code == 200
    assert grant_response.json()["email"] == "member@example.com"
    assert grant_response.json()["is_admin"] is True

    with TestClient(create_app()) as client:
        member_login = client.post(
            "/auth/login",
            json={
                "email": "member@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        member_admin_response = client.get("/admin/settings/overview")

    assert member_login.status_code == 200
    assert member_login.json()["is_admin"] is True
    assert member_admin_response.status_code == 200


def test_admin_account_sync_summary_reports_mirror_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'auth-admin-sync.db'}")
    monkeypatch.setenv("ADMIN_EMAILS_CSV", "admin@example.com")

    with TestClient(create_app()) as client:
        client.post(
            "/auth/register",
            json={
                "name": "admin",
                "email": "admin@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        client.post(
            "/auth/login",
            json={
                "email": "admin@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        created_response = client.post(
            "/admin/accounts",
            json={
                "name": "mirrored",
                "email": "mirrored@example.com",
                "is_admin": False,
                "public_account_id": "acct_public_1",
                "public_workspace_id": "ws_public_1",
            },
        )
        summary_response = client.get("/admin/account-sync/summary")

    assert created_response.status_code == 201
    assert created_response.json()["email"] == "mirrored@example.com"
    assert summary_response.status_code == 200
    assert summary_response.json() == {
        "total_accounts": 2,
        "mirrored_accounts": 1,
        "accounts_needing_backfill": 1,
        "accounts_with_pending_sync": 0,
        "accounts_with_failed_sync": 0,
        "accounts_fully_converged": 1,
    }


def test_admin_can_soft_delete_account(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'auth-admin-delete-account.db'}")
    monkeypatch.setenv("ADMIN_EMAILS_CSV", "admin@example.com")

    with TestClient(create_app()) as client:
        client.post(
            "/auth/register",
            json={
                "name": "admin",
                "email": "admin@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        client.post(
            "/auth/login",
            json={
                "email": "admin@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        created_response = client.post(
            "/admin/accounts",
            json={"name": "deleted-member", "email": "deleted@example.com"},
        )
        delete_response = client.delete(f"/admin/accounts/{created_response.json()['id']}")
        list_response = client.get("/admin/accounts")

    assert created_response.status_code == 201
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"
    assert any(row["email"] == "deleted@example.com" and row["status"] == "deleted" for row in list_response.json())


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
