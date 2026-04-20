from fastapi.testclient import TestClient

from app.main import create_app


def _create_account_and_key(client: TestClient, *, per_minute: int | None = None) -> tuple[int, str, int]:
    account_response = client.post(
        "/admin/accounts",
        json={"name": "account-one"},
        headers={"x-admin-secret": "change-me"},
    )
    account_id = account_response.json()["id"]
    key_response = client.post(
        "/admin/api-keys",
        json={
            "account_id": account_id,
            "name": "key-one",
            "per_minute": per_minute,
        },
        headers={"x-admin-secret": "change-me"},
    )
    return account_id, key_response.json()["api_key"], key_response.json()["id"]


def test_admin_can_create_and_list_accounts_and_keys(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        account_id, api_key, key_id = _create_account_and_key(client)
        accounts_response = client.get("/admin/accounts", headers={"x-admin-secret": "change-me"})
        keys_response = client.get("/admin/api-keys", headers={"x-admin-secret": "change-me"})

    assert account_id > 0
    assert api_key.startswith("agk_")
    assert accounts_response.status_code == 200
    assert keys_response.status_code == 200
    assert accounts_response.json()[0]["name"] == "account-one"
    assert keys_response.json()[0]["id"] == key_id
    assert keys_response.json()[0]["key_prefix"]


def test_revoked_api_key_cannot_access_openai_routes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        _, api_key, key_id = _create_account_and_key(client)
        revoke_response = client.post(
            f"/admin/api-keys/{key_id}/revoke",
            headers={"x-admin-secret": "change-me"},
        )
        models_response = client.get(
            "/v1/models",
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert revoke_response.status_code == 200
    assert models_response.status_code == 401
    assert models_response.json() == {"detail": "api key is not active"}


def test_openai_routes_require_bearer_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        response = client.get("/v1/models")

    assert response.status_code == 401
    assert response.json() == {"detail": "missing bearer token"}


def test_api_key_per_minute_limit_is_enforced(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        _, api_key, key_id = _create_account_and_key(client, per_minute=1)
        provider_response = client.post(
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
        assert provider_response.status_code == 201

        first_response = client.get(
            "/v1/models",
            headers={"authorization": f"Bearer {api_key}"},
        )
        second_response = client.get(
            "/v1/models",
            headers={"authorization": f"Bearer {api_key}"},
        )
        usage_response = client.get(
            f"/admin/api-keys/{key_id}/usage",
            headers={"x-admin-secret": "change-me"},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.json() == {"detail": "minute rate limit exceeded"}
    assert usage_response.status_code == 200
    assert usage_response.json()["limited_requests"] == 1
