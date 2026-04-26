from fastapi.testclient import TestClient

from app.main import create_app


def _create_account_and_key(client: TestClient, *, per_minute: int | None = None) -> tuple[int, str, int]:
    account_response = client.post(
        "/admin/accounts",
        json={"name": "account-one"},
        headers={"x-admin-secret": "change-me"},
    )
    account_id = account_response.json()["id"]
    client.post(
        f"/admin/accounts/{account_id}/credits/adjust",
        json={"credits_delta": 5000, "notes": "test credits"},
        headers={"x-admin-secret": "change-me"},
    )
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


def test_admin_can_update_and_delete_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        _, _, key_id = _create_account_and_key(client)
        update_response = client.patch(
            f"/admin/api-keys/{key_id}",
            json={
                "name": "edited-key",
                "per_minute": 3,
                "per_hour": 30,
                "per_day": 300,
                "status": "active",
            },
            headers={"x-admin-secret": "change-me"},
        )
        delete_response = client.delete(
            f"/admin/api-keys/{key_id}",
            headers={"x-admin-secret": "change-me"},
        )

    assert update_response.status_code == 200
    assert update_response.json()["name"] == "edited-key"
    assert update_response.json()["per_minute"] == 3
    assert update_response.json()["per_hour"] == 30
    assert update_response.json()["per_day"] == 300
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "revoked"


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


def test_admin_usage_summary_exposes_provider_and_model_activity(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        _, api_key, key_id = _create_account_and_key(client)
        completion_response = client.post(
            "/v1/chat/completions",
            json={
                "model": "missing:default",
                "messages": [{"role": "user", "content": "hello"}],
            },
            headers={"authorization": f"Bearer {api_key}"},
        )
        assert completion_response.status_code == 404

        response = client.get(
            f"/admin/api-keys/{key_id}/usage",
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 200
    assert response.json()["total_requests"] == 1
    assert response.json()["by_provider"] == {"missing": 1}
    assert response.json()["by_model"] == {"missing:default": 1}


def test_admin_usage_overview_batches_key_activity(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        _, api_key, _ = _create_account_and_key(client)
        completion_response = client.post(
            "/v1/chat/completions",
            json={
                "model": "missing:default",
                "messages": [{"role": "user", "content": "hello"}],
            },
            headers={"authorization": f"Bearer {api_key}"},
        )
        assert completion_response.status_code == 404

        response = client.get(
            "/admin/usage/overview",
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["by_provider"] == {"missing": 1}
    assert payload["by_model"] == {"missing:default": 1}
    assert payload["key_activity"][0]["total_requests"] == 1


def test_admin_can_list_usage_records_as_table_rows(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        account_id, api_key, key_id = _create_account_and_key(client)
        completion_response = client.post(
            "/v1/chat/completions",
            json={
                "model": "missing:default",
                "messages": [{"role": "user", "content": "hello"}],
            },
            headers={"authorization": f"Bearer {api_key}"},
        )
        assert completion_response.status_code == 404

        response = client.get(
            "/admin/usage/records",
            headers={"x-admin-secret": "change-me"},
        )
        filtered_response = client.get(
            f"/admin/usage/records?account_id={account_id}&api_key_id={key_id}&provider_name=missing",
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["account_id"] == account_id
    assert rows[0]["account_name"] == "account-one"
    assert rows[0]["api_key_id"] == key_id
    assert rows[0]["api_key_name"] == "key-one"
    assert rows[0]["key_prefix"]
    assert rows[0]["provider_name"] == "missing"
    assert rows[0]["model_id"] == "missing:default"
    assert rows[0]["outcome"] == "error"
    assert filtered_response.status_code == 200
    assert filtered_response.json()[0]["id"] == rows[0]["id"]
