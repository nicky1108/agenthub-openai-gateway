import sqlite3

from fastapi.testclient import TestClient

from app.main import create_app


def _create_account(client: TestClient, name: str) -> int:
    response = client.post(
        "/admin/accounts",
        json={"name": name},
        headers={"x-admin-secret": "change-me"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_api_key(client: TestClient, account_id: int, name: str) -> tuple[int, str]:
    response = client.post(
        "/admin/api-keys",
        json={"account_id": account_id, "name": name},
        headers={"x-admin-secret": "change-me"},
    )
    assert response.status_code == 201
    return response.json()["id"], response.json()["api_key"]


def test_internal_contract_rejects_missing_service_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("PUBLIC_GATEWAY_SERVICE_TOKEN", "public-gateway-token")

    with TestClient(create_app()) as client:
        response = client.post(
            "/internal/public-gateway/introspect-key",
            json={"token": "agk_test_token"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid public gateway token"}


def test_internal_introspection_returns_expected_identity_shape(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("PUBLIC_GATEWAY_SERVICE_TOKEN", "public-gateway-token")

    with TestClient(create_app()) as client:
        account_id = _create_account(client, "public-gateway-contract")
        api_key_id, api_key = _create_api_key(client, account_id, "public-gateway-key")

        response = client.post(
            "/internal/public-gateway/introspect-key",
            json={"token": api_key},
            headers={"x-public-gateway-token": "public-gateway-token"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "account_id": str(account_id),
        "workspace_id": f"ws_test_account_{account_id}",
        "api_key_id": str(api_key_id),
        "status": "active",
    }


def test_internal_models_returns_platform_catalog(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("PUBLIC_GATEWAY_SERVICE_TOKEN", "public-gateway-token")

    with TestClient(create_app()) as client:
        create_response = client.post(
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
        assert create_response.status_code == 201

        response = client.get(
            "/internal/public-gateway/models",
            headers={"x-public-gateway-token": "public-gateway-token"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    assert payload["object"] == "list"
    assert any(model["id"] == "codex:gpt-5.4" for model in payload["data"])


def test_internal_usage_events_record_usage_without_deducting_credits(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("PUBLIC_GATEWAY_SERVICE_TOKEN", "public-gateway-token")

    database_path = tmp_path / "gateway.db"

    with TestClient(create_app()) as client:
        account_id = _create_account(client, "usage-event-account")
        api_key_id, _api_key = _create_api_key(client, account_id, "usage-event-key")
        adjust_response = client.post(
            f"/admin/accounts/{account_id}/credits/adjust",
            json={"credits_delta": 500, "notes": "bootstrap"},
            headers={"x-admin-secret": "change-me"},
        )
        assert adjust_response.status_code == 200

        response = client.post(
            "/internal/public-gateway/usage-events",
            json={
                "account_id": str(account_id),
                "workspace_id": f"ws_test_account_{account_id}",
                "api_key_id": str(api_key_id),
                "provider_name": "custom-provider",
                "model_id": "custom-provider:default",
                "source": "custom",
                "billable": False,
                "credits_delta": 0,
                "outcome": "success",
            },
            headers={"x-public-gateway-token": "public-gateway-token"},
        )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}

    database = sqlite3.connect(database_path)
    try:
        usage_row = database.execute(
            """
            SELECT account_id, api_key_id, provider_name, model_id, outcome, credits_charged, pricing_source, token_source
            FROM usage_records
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        balance_row = database.execute(
            "SELECT credit_balance FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        ledger_count = database.execute("SELECT COUNT(*) FROM credit_ledger").fetchone()
    finally:
        database.close()

    assert usage_row == (
        account_id,
        api_key_id,
        "custom-provider",
        "custom-provider:default",
        "success",
        0,
        "custom",
        "custom",
    )
    assert balance_row == (500,)
    assert ledger_count == (1,)


def test_internal_account_upsert_and_key_sync_routes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("PUBLIC_GATEWAY_SERVICE_TOKEN", "public-gateway-token")

    with TestClient(create_app()) as client:
        account_response = client.post(
            "/internal/public-gateway/accounts/upsert",
            json={
                "id": "1",
                "workspace_id": "ws_public_account_1",
                "name": "Public Account",
                "email": "public@example.com",
                "status": "active",
            },
            headers={"x-public-gateway-token": "public-gateway-token"},
        )
        key_response = client.post(
            "/internal/public-gateway/api-keys/upsert",
            json={
                "id": "10",
                "account_id": "1",
                "name": "Primary",
                "key_prefix": "abc12345",
                "secret_hash": "deadbeef",
                "status": "active",
                "per_minute": 10,
                "per_hour": 100,
                "per_day": 1000,
            },
            headers={"x-public-gateway-token": "public-gateway-token"},
        )
        revoke_response = client.post(
            "/internal/public-gateway/api-keys/revoke",
            json={
                "id": "10",
                "account_id": "1",
                "name": "Primary",
                "key_prefix": "abc12345",
                "secret_hash": "deadbeef",
                "status": "revoked",
            },
            headers={"x-public-gateway-token": "public-gateway-token"},
        )

    assert account_response.status_code == 200
    assert key_response.status_code == 200
    assert revoke_response.status_code == 200

    database = sqlite3.connect(tmp_path / "gateway.db")
    try:
        account_row = database.execute(
            "SELECT public_account_id, public_workspace_id, email, status FROM accounts"
        ).fetchone()
        api_key_row = database.execute(
            "SELECT public_api_key_id, key_prefix, secret_hash, status FROM api_keys"
        ).fetchone()
    finally:
        database.close()

    assert account_row == ("1", "ws_public_account_1", "public@example.com", "active")
    assert api_key_row == ("10", "abc12345", "deadbeef", "revoked")


def test_internal_account_mirror_status_route_returns_local_ids(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("PUBLIC_GATEWAY_SERVICE_TOKEN", "public-gateway-token")

    with TestClient(create_app()) as client:
        client.post(
            "/internal/public-gateway/accounts/upsert",
            json={
                "id": "3",
                "workspace_id": "ws_public_account_3",
                "name": "Tunnel Sync",
                "email": "tunnel-sync@example.com",
                "status": "active",
            },
            headers={"x-public-gateway-token": "public-gateway-token"},
        )
        client.post(
            "/internal/public-gateway/api-keys/upsert",
            json={
                "id": "5",
                "account_id": "3",
                "name": "tunnel-primary",
                "key_prefix": "903f369d",
                "secret_hash": "deadbeef",
                "status": "active",
                "per_minute": None,
                "per_hour": None,
                "per_day": None,
            },
            headers={"x-public-gateway-token": "public-gateway-token"},
        )
        response = client.get(
            "/internal/public-gateway/accounts/3/mirror",
            headers={"x-public-gateway-token": "public-gateway-token"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "public_account_id": "3",
        "workspace_id": "ws_public_account_3",
        "local_account_id": "1",
        "email": "tunnel-sync@example.com",
        "status": "active",
        "api_keys": [
            {
                "public_api_key_id": "5",
                "local_api_key_id": "1",
                "name": "tunnel-primary",
                "key_prefix": "903f369d",
                "status": "active",
            }
        ],
    }
