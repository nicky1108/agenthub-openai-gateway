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
