import httpx
from fastapi.testclient import TestClient

from app.main import create_app


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


def test_portal_dashboard_reads_local_balance_usage_and_ledger(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        _register_and_login(client)
        key_response = client.post("/portal/api-keys?name=primary")
        assert key_response.status_code == 201
        api_key = key_response.json()["api_key"]

        credit_response = client.post(
            "/admin/accounts/1/credits/adjust",
            json={"credits_delta": 2500, "notes": "initial balance"},
            headers={"x-admin-secret": "change-me"},
        )
        assert credit_response.status_code == 200

        models_response = client.get(
            "/v1/models",
            headers={"authorization": f"Bearer {api_key}"},
        )
        assert models_response.status_code == 200

        dashboard_response = client.get("/portal/dashboard")

    assert dashboard_response.status_code == 200
    payload = dashboard_response.json()
    assert payload["credits_balance"] == 2500
    assert payload["api_key_count"] == 1
    assert payload["request_count_24h"] == 1
    assert payload["request_count_7d"] == 1
    assert payload["platform_requests_24h"] == 1
    assert payload["custom_requests_24h"] == 0
    assert payload["local_provider_count"] == 0
    assert payload["recent_usage"][0]["outcome"] == "success"
    assert payload["credit_ledger"][0]["entry_type"] == "manual_adjustment"


def test_portal_dashboard_requires_session_cookie(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        response = client.get("/portal/dashboard")

    assert response.status_code == 401
    assert response.json() == {"detail": "missing session cookie"}


def test_portal_provider_presets_include_mainstream_and_other_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        _register_and_login(client)
        response = client.get("/portal/provider-presets")

    assert response.status_code == 200
    presets = response.json()
    preset_ids = {preset["id"] for preset in presets}
    assert {"openai-api", "minimax-cn", "claude", "other-openai-compatible"}.issubset(preset_ids)
    other = next(preset for preset in presets if preset["id"] == "other-openai-compatible")
    assert other["protocol"] == "openai"


def test_user_api_key_lifecycle_is_local_to_account(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        _register_and_login(client)
        create_response = client.post(
            "/portal/api-keys?name=primary&per_minute=2&per_hour=10&per_day=20"
        )
        assert create_response.status_code == 201
        created = create_response.json()

        list_response = client.get("/portal/api-keys")
        patch_response = client.patch(
            f"/portal/api-keys/{created['id']}",
            json={"name": "renamed", "per_minute": 3},
        )
        delete_response = client.post(f"/portal/api-keys/{created['id']}/revoke")
        models_response = client.get(
            "/v1/models",
            headers={"authorization": f"Bearer {created['api_key']}"},
        )

    assert created["api_key"].startswith("agk_")
    assert list_response.status_code == 200
    assert list_response.json()[0]["key_prefix"] == created["key_prefix"]
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "renamed"
    assert patch_response.json()["per_minute"] == 3
    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "revoked"}
    assert models_response.status_code == 401
    assert models_response.json() == {"detail": "api key is not active"}


def test_legacy_user_self_service_routes_remain_available(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        _register_and_login(client)
        create_response = client.post("/user/api-keys?name=legacy")
        list_response = client.get("/user/api-keys")
        delete_response = client.delete(f"/user/api-keys/{create_response.json()['id']}")

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    assert list_response.json()[0]["name"] == "legacy"
    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "revoked"}


def test_user_provider_crud_and_catalog_are_local_to_account(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        _register_and_login(client)
        create_response = client.post(
            "/portal/providers?name=minimax-cn&protocol=openai"
            "&base_url=https://api.minimaxi.com/v1&api_key=provider-secret&description=demo"
        )
        assert create_response.status_code == 201
        provider = create_response.json()

        list_response = client.get("/portal/providers")
        catalog_response = client.get("/portal/catalog")
        update_response = client.patch(
            f"/portal/providers/{provider['id']}",
            json={
                "name": "MiniMax CN",
                "base_url": "https://api.minimaxi.com/v1",
                "api_key": "updated-secret",
            },
        )
        delete_response = client.delete(f"/portal/providers/{provider['id']}")
        final_list_response = client.get("/portal/providers")

    assert provider["slug"] == "minimax-cn"
    assert provider["protocol"] == "openai"
    assert "secret_ref" not in provider
    assert list_response.status_code == 200
    assert list_response.json()[0]["slug"] == "minimax-cn"
    assert catalog_response.status_code == 200
    assert "minimax-cn:MiniMax-M2.7" in {
        item["id"] for item in catalog_response.json()["custom_models"]
    }
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "MiniMax CN"
    assert update_response.json()["last_probe_ok"] is None
    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "deleted"}
    assert final_list_response.json() == []


def test_user_provider_rejects_reserved_slug_and_private_url(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        _register_and_login(client)
        reserved_response = client.post(
            "/portal/providers?name=codex&protocol=openai"
            "&base_url=https://api.example.com/v1&api_key=provider-secret"
        )
        private_url_response = client.post(
            "/portal/providers?name=unsafe&protocol=openai"
            "&base_url=http://127.0.0.1:9999/v1&api_key=provider-secret"
        )

    assert reserved_response.status_code == 400
    assert reserved_response.json() == {"detail": "reserved provider slug"}
    assert private_url_response.status_code == 400
    assert private_url_response.json() == {"detail": "unsafe provider url"}


class FakeProbeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, path: str) -> httpx.Response:
        request = httpx.Request("GET", f"https://provider.test{path}")
        return httpx.Response(status_code=404, request=request)

    async def post(self, path: str, json: dict[str, object]) -> httpx.Response:
        request = httpx.Request("POST", f"https://provider.test{path}")
        if json["model"] == "MiniMax-M2.7":
            return httpx.Response(
                status_code=200,
                json={"choices": [{"message": {"role": "assistant", "content": "OK"}}]},
                request=request,
            )
        return httpx.Response(status_code=400, json={"detail": "bad model"}, request=request)


class FakeAnthropicProbeAdapter:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def list_models(self) -> list[str]:
        return ["claude-sonnet-4-20250514", "gpt-4-turbo"]

    async def chat(self, request) -> dict[str, object]:
        assert request.provider_model == "claude-sonnet-4-20250514"
        return {
            "object": "chat.completion",
            "choices": [{"message": {"role": "assistant", "content": "OK"}}],
        }


def test_existing_provider_probe_persists_last_probe_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setattr("app.api.user.httpx.AsyncClient", FakeProbeAsyncClient)

    with TestClient(create_app()) as client:
        _register_and_login(client)
        provider_response = client.post(
            "/portal/providers?name=minimax-cn&base_url=https://api.minimaxi.com/v1&api_key=provider-secret",
        )
        assert provider_response.status_code == 201

        provider_id = provider_response.json()["id"]
        probe_response = client.post(f"/portal/providers/{provider_id}/probe")
        providers_response = client.get("/portal/providers")

    assert probe_response.status_code == 200
    assert probe_response.json()["last_probe_ok"] is True
    assert probe_response.json()["last_probe_model"] == "MiniMax-M2.7"
    assert probe_response.json()["last_detected_models"] == []
    assert probe_response.json()["last_probe_detail"] is None
    assert probe_response.json()["last_probe_at"] is not None
    assert providers_response.json()[0]["last_probe_ok"] is True


def test_anthropic_provider_probe_uses_messages_protocol(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setattr("app.api.user.AnthropicMessagesAdapter", FakeAnthropicProbeAdapter)

    with TestClient(create_app()) as client:
        _register_and_login(client)
        response = client.post(
            "/portal/providers/probe",
            json={
                "protocol": "anthropic",
                "base_url": "https://api.anthropic.com/v1",
                "api_key": "provider-secret",
                "candidate_models": ["claude-sonnet-4-20250514"],
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "models_endpoint_supported": True,
        "detected_models": ["claude-sonnet-4-20250514"],
        "completion_probe_ok": True,
        "completion_probe_model": "claude-sonnet-4-20250514",
        "detail": None,
    }


def test_v1_models_includes_current_account_custom_models(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        _register_and_login(client)
        key_response = client.post("/portal/api-keys?name=primary")
        provider_response = client.post(
            "/portal/providers?name=minimax-cn&protocol=openai"
            "&base_url=https://api.minimaxi.com/v1&api_key=provider-secret"
        )
        assert key_response.status_code == 201
        assert provider_response.status_code == 201

        models_response = client.get(
            "/v1/models",
            headers={"authorization": f"Bearer {key_response.json()['api_key']}"},
        )

    assert models_response.status_code == 200
    model_ids = {item["id"] for item in models_response.json()["data"]}
    assert "minimax-cn:MiniMax-M2.7" in model_ids


def test_custom_provider_non_stream_chat_records_local_usage(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    captured: dict[str, object] = {}

    async def fake_route_custom_completion(request_payload, provider):
        captured["request_payload"] = request_payload
        captured["provider"] = provider
        return {
            "id": "chatcmpl_custom",
            "object": "chat.completion",
            "model": request_payload["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "OK"},
                    "finish_reason": "stop",
                }
            ],
        }

    monkeypatch.setattr("app.api.openai.route_custom_completion", fake_route_custom_completion)

    with TestClient(create_app()) as client:
        _register_and_login(client)
        key_response = client.post("/portal/api-keys?name=primary")
        provider_response = client.post(
            "/portal/providers?name=minimax-cn&protocol=openai"
            "&base_url=https://api.minimaxi.com/v1&api_key=provider-secret"
        )
        assert key_response.status_code == 201
        assert provider_response.status_code == 201

        chat_response = client.post(
            "/v1/chat/completions",
            json={
                "model": "minimax-cn:MiniMax-M2.7",
                "messages": [{"role": "user", "content": "Reply only OK"}],
                "stream": False,
            },
            headers={"authorization": f"Bearer {key_response.json()['api_key']}"},
        )
        dashboard_response = client.get("/portal/dashboard")

    assert chat_response.status_code == 200
    assert chat_response.json()["choices"][0]["message"]["content"] == "OK"
    assert captured["request_payload"]["model"] == "minimax-cn:MiniMax-M2.7"
    assert captured["provider"].slug == "minimax-cn"
    assert dashboard_response.json()["custom_requests_24h"] == 1
    assert dashboard_response.json()["platform_requests_24h"] == 0


def test_unknown_bare_model_returns_stable_404(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        _register_and_login(client)
        key_response = client.post("/portal/api-keys?name=primary")
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "missing-custom",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
            headers={"authorization": f"Bearer {key_response.json()['api_key']}"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "model or provider 'missing-custom' not found"}
