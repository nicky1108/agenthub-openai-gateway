import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.base import ChatRequest
from app.adapters.http.openai_compatible import OpenAICompatibleHttpAdapter
from app.core.secrets import is_sealed_secret, reveal_secret, seal_secret
from app.main import create_app
from app.services.custom_provider_runtime import CustomProviderRequestError, execute_custom_completion
from app.services.provider_guardrails import ensure_safe_provider_url


def test_provider_url_rejects_hostname_that_resolves_to_private_ip() -> None:
    with pytest.raises(ValueError, match="unsafe provider url"):
        ensure_safe_provider_url(
            "https://provider.example/v1",
            resolver=lambda _host: ["169.254.169.254"],
        )


@pytest.mark.asyncio
async def test_custom_provider_runtime_revalidates_resolved_host_before_network(monkeypatch) -> None:
    async def _transport(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("unsafe provider must be blocked before issuing a request")

    monkeypatch.setattr(
        "app.services.provider_guardrails._default_resolver",
        lambda _host: ["127.0.0.1"],
    )

    with pytest.raises(CustomProviderRequestError, match="unsafe provider url"):
        await execute_custom_completion(
            {
                "model": "unsafe:default",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
            {
                "slug": "unsafe",
                "base_url": "https://unsafe.example/v1",
                "secret_value": "upstream-secret",
                "protocol": "openai",
            },
            provider_transport=httpx.MockTransport(_transport),
        )


def test_auth_session_cookie_is_secure_and_expiring_for_https_frontend(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://openhubs.xyz")

    with TestClient(create_app()) as client:
        response = client.post(
            "/auth/register",
            json={
                "name": "secure-cookie",
                "email": "secure-cookie@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )

    set_cookie = response.headers["set-cookie"]
    assert response.status_code == 201
    assert "agh_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Secure" in set_cookie
    assert "Max-Age=604800" in set_cookie


def test_login_rate_limit_blocks_repeated_invalid_credentials(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("AUTH_LOGIN_RATE_LIMIT_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300")

    with TestClient(create_app()) as client:
        first = client.post(
            "/auth/login",
            json={"email": "missing@example.com", "password": "bad"},
        )
        second = client.post(
            "/auth/login",
            json={"email": "missing@example.com", "password": "bad"},
        )
        third = client.post(
            "/auth/login",
            json={"email": "missing@example.com", "password": "bad"},
        )

    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    assert third.json() == {"detail": "too many login attempts"}


def test_production_rejects_default_runtime_secrets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("APP_ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="ADMIN_SECRET"):
        with TestClient(create_app()):
            pass


def test_admin_cli_provider_management_requires_explicit_production_opt_in(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    monkeypatch.setenv("ADMIN_EMAILS_CSV", "")
    monkeypatch.setenv("ADMIN_SECRET", "prod-admin-secret")
    monkeypatch.setenv("PUBLIC_GATEWAY_SERVICE_TOKEN", "prod-public-token")
    monkeypatch.setenv("SECRET_ENCRYPTION_KEY", "prod-secret-encryption-key-with-at-least-32-chars")

    with TestClient(create_app()) as client:
        response = client.post(
            "/admin/providers",
            json={
                "name": "shell",
                "http_enabled": False,
                "cli_enabled": True,
                "route_policy": "fixed-cli",
                "cli_command": "/bin/echo",
            },
            headers={"x-admin-secret": "prod-admin-secret"},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "CLI provider management is disabled"}


def test_provider_secrets_are_encrypted_at_rest_and_redacted_from_admin_reads(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "gateway.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")
    monkeypatch.setenv("ADMIN_EMAILS_CSV", "")
    monkeypatch.setenv("SECRET_ENCRYPTION_KEY", "test-secret-encryption-key-with-at-least-32-chars")

    with TestClient(create_app()) as client:
        create_response = client.post(
            "/admin/providers",
            json={
                "name": "secure-http",
                "http_enabled": True,
                "cli_enabled": False,
                "route_policy": "fixed-http",
                "http_base_url": "https://provider.example/v1",
                "http_api_key": "upstream-secret",
                "http_headers_json": '{"X-Secret": "header-secret"}',
            },
            headers={"x-admin-secret": "change-me"},
        )
        list_response = client.get(
            "/admin/providers",
            headers={"x-admin-secret": "change-me"},
        )

    assert create_response.status_code == 201
    assert create_response.json()["http_api_key"] is None
    assert create_response.json()["http_api_key_configured"] is True
    assert create_response.json()["http_headers_json"] == "{}"
    assert list_response.json()[0]["http_api_key"] is None

    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            "SELECT http_api_key, http_headers_json FROM providers WHERE name = 'secure-http'"
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    assert row[0] != "upstream-secret"
    assert row[1] != '{"X-Secret": "header-secret"}'
    assert is_sealed_secret(row[0])
    assert is_sealed_secret(row[1])
    assert reveal_secret(row[0]) == "upstream-secret"
    assert reveal_secret(row[1]) == '{"X-Secret": "header-secret"}'


def test_user_provider_secret_is_encrypted_at_rest(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "gateway.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")
    monkeypatch.setenv("SECRET_ENCRYPTION_KEY", "test-secret-encryption-key-with-at-least-32-chars")

    with TestClient(create_app()) as client:
        register_response = client.post(
            "/auth/register",
            json={
                "name": "portal-secure",
                "email": "portal-secure@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        provider_response = client.post(
            "/portal/providers?name=custom-provider&protocol=openai"
            "&base_url=https://provider.example/v1&api_key=provider-secret"
        )

    assert register_response.status_code == 201
    assert provider_response.status_code == 201
    assert "secret_ref" not in provider_response.json()

    connection = sqlite3.connect(database_path)
    try:
        stored_secret = connection.execute(
            "SELECT secret_ref FROM user_providers WHERE slug = 'custom-provider'"
        ).fetchone()[0]
    finally:
        connection.close()

    assert stored_secret != "provider-secret"
    assert is_sealed_secret(stored_secret)
    assert reveal_secret(stored_secret) == "provider-secret"


def test_secret_sealing_round_trips_and_accepts_legacy_plaintext(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_ENCRYPTION_KEY", "test-secret-encryption-key-with-at-least-32-chars")

    sealed = seal_secret("upstream-secret")

    assert is_sealed_secret(sealed)
    assert sealed != "upstream-secret"
    assert reveal_secret(sealed) == "upstream-secret"
    assert reveal_secret("legacy-plaintext") == "legacy-plaintext"


@pytest.mark.asyncio
async def test_openai_http_adapter_uses_explicit_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}
    real_async_client = httpx.AsyncClient

    class CapturingAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            captured.update(kwargs)
            self._client = real_async_client(
                *args,
                **{key: value for key, value in kwargs.items() if key != "timeout"},
                timeout=kwargs["timeout"],
            )

        async def __aenter__(self):
            await self._client.__aenter__()
            return self._client

        async def __aexit__(self, exc_type, exc, tb):
            return await self._client.__aexit__(exc_type, exc, tb)

    monkeypatch.setattr("app.adapters.http.openai_compatible.httpx.AsyncClient", CapturingAsyncClient)

    adapter = OpenAICompatibleHttpAdapter(
        base_url="https://provider.example/v1",
        api_key="test-key",
        headers={},
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"object": "chat.completion", "choices": []})),
    )
    await adapter.chat(
        ChatRequest(
            provider_name="custom",
            provider_model="default",
            messages=[{"role": "user", "content": "hello"}],
            stream=False,
        )
    )

    assert isinstance(captured["timeout"], httpx.Timeout)
