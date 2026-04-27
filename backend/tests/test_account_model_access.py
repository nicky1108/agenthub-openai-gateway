from fastapi.testclient import TestClient

from app.main import create_app


def _create_account_and_key(client: TestClient, name: str = "model-access-account") -> tuple[int, str]:
    account_response = client.post(
        "/admin/accounts",
        json={"name": name},
        headers={"x-admin-secret": "change-me"},
    )
    assert account_response.status_code == 201
    key_response = client.post(
        "/admin/api-keys",
        json={"account_id": account_response.json()["id"], "name": f"{name}-key"},
        headers={"x-admin-secret": "change-me"},
    )
    assert key_response.status_code == 201
    return account_response.json()["id"], key_response.json()["api_key"]


def _create_codex_provider(client: TestClient) -> None:
    response = client.post(
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
    assert response.status_code == 201


def _register_and_login(client: TestClient) -> None:
    register_response = client.post(
        "/auth/register",
        json={
            "name": "portal-user",
            "email": "portal@example.com",
            "password": "CorrectHorseBatteryStaple1!",
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={
            "email": "portal@example.com",
            "password": "CorrectHorseBatteryStaple1!",
        },
    )
    assert login_response.status_code == 200


def test_admin_can_restrict_platform_model_visibility_per_account(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("CODEX_MODELS_CACHE_FILE", str(tmp_path / "missing-codex-models.json"))

    with TestClient(create_app()) as client:
        account_id, api_key = _create_account_and_key(client)
        _create_codex_provider(client)

        default_access_response = client.get(
            f"/admin/accounts/{account_id}/model-access",
            headers={"x-admin-secret": "change-me"},
        )
        update_response = client.put(
            f"/admin/accounts/{account_id}/model-access",
            json={
                "platform_model_access_mode": "allowlist",
                "allowed_model_ids": ["codex:gpt-5.4"],
            },
            headers={"x-admin-secret": "change-me"},
        )
        models_response = client.get("/v1/models", headers={"authorization": f"Bearer {api_key}"})
        hidden_chat_response = client.post(
            "/v1/chat/completions",
            json={
                "model": "codex:gpt-5.5",
                "messages": [{"role": "user", "content": "hello"}],
            },
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert default_access_response.status_code == 200
    default_payload = default_access_response.json()
    assert default_payload["platform_model_access_mode"] == "all"
    assert "codex:gpt-5.4" in {item["id"] for item in default_payload["available_models"]}

    assert update_response.status_code == 200
    assert update_response.json()["platform_model_access_mode"] == "allowlist"
    assert update_response.json()["allowed_model_ids"] == ["codex:gpt-5.4"]

    assert models_response.status_code == 200
    visible_model_ids = {item["id"] for item in models_response.json()["data"]}
    assert "codex:gpt-5.4" in visible_model_ids
    assert "codex:gpt-5.5" not in visible_model_ids

    assert hidden_chat_response.status_code == 404
    assert hidden_chat_response.json() == {"detail": "model or provider 'codex:gpt-5.5' not found"}


def test_account_platform_model_allowlist_does_not_hide_custom_models(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("CODEX_MODELS_CACHE_FILE", str(tmp_path / "missing-codex-models.json"))

    with TestClient(create_app()) as client:
        _register_and_login(client)
        _create_codex_provider(client)
        custom_provider_response = client.post(
            "/portal/providers?name=minimax-cn&protocol=openai"
            "&base_url=https://api.minimaxi.com/v1&api_key=provider-secret&description=demo"
        )
        assert custom_provider_response.status_code == 201

        update_response = client.put(
            "/admin/accounts/1/model-access",
            json={
                "platform_model_access_mode": "allowlist",
                "allowed_model_ids": ["codex:gpt-5.4"],
            },
            headers={"x-admin-secret": "change-me"},
        )
        catalog_response = client.get("/portal/catalog")

    assert update_response.status_code == 200
    assert catalog_response.status_code == 200
    catalog_payload = catalog_response.json()
    assert {item["id"] for item in catalog_payload["platform_models"]} == {"codex:gpt-5.4"}
    assert "minimax-cn:MiniMax-M2.7" in {item["id"] for item in catalog_payload["custom_models"]}


def test_portal_hides_hermes_until_account_is_admin_and_granted(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("CODEX_MODELS_CACHE_FILE", str(tmp_path / "missing-codex-models.json"))
    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.setenv("HERMES_MODEL", "hermes-agent")

    with TestClient(create_app()) as client:
        _register_and_login(client)
        default_catalog_response = client.get("/portal/catalog")
        non_admin_grant_response = client.put(
            "/admin/accounts/1/model-access",
            json={
                "platform_model_access_mode": "all",
                "allowed_model_ids": ["hermes:hermes-agent"],
            },
            headers={"x-admin-secret": "change-me"},
        )
        non_admin_granted_catalog_response = client.get("/portal/catalog")
        admin_response = client.patch(
            "/admin/accounts/1",
            json={"is_admin": True},
            headers={"x-admin-secret": "change-me"},
        )
        admin_grant_response = client.put(
            "/admin/accounts/1/model-access",
            json={
                "platform_model_access_mode": "all",
                "allowed_model_ids": ["hermes:hermes-agent"],
            },
            headers={"x-admin-secret": "change-me"},
        )
        admin_granted_catalog_response = client.get("/portal/catalog")
        admin_model_access_response = client.get(
            "/admin/accounts/1/model-access",
            headers={"x-admin-secret": "change-me"},
        )

    assert default_catalog_response.status_code == 200
    assert "hermes:hermes-agent" not in {
        item["id"] for item in default_catalog_response.json()["platform_models"]
    }
    assert non_admin_grant_response.status_code == 422
    assert non_admin_grant_response.json() == {
        "detail": "admin permission required for platform model: hermes:hermes-agent"
    }
    assert "hermes:hermes-agent" not in {
        item["id"] for item in non_admin_granted_catalog_response.json()["platform_models"]
    }
    assert admin_response.status_code == 200
    assert admin_response.json()["is_admin"] is True
    assert admin_grant_response.status_code == 200
    assert "hermes:hermes-agent" in {
        item["id"] for item in admin_granted_catalog_response.json()["platform_models"]
    }
    assert admin_model_access_response.json()["platform_model_access_mode"] == "all"
    assert admin_model_access_response.json()["allowed_model_ids"] == ["hermes:hermes-agent"]
