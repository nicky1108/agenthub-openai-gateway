import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.base import ChatRequest
from app.adapters.http.base import MockHttpAdapter
from app.api.admin import chat_orchestrator
from app.main import create_app


@pytest.fixture(autouse=True)
def use_secret_admin(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_EMAILS_CSV", "")


def test_admin_test_chat_returns_chat_completion_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setattr(chat_orchestrator, "_http_adapter", lambda provider: MockHttpAdapter())

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

        response = client.post(
            "/admin/test-chat",
            json={
                "model": "codex:gpt-5.4",
                "messages": [{"role": "user", "content": "ping"}],
            },
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "mocked-http-response"


def test_admin_test_chat_rejects_disabled_provider_model(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setattr(chat_orchestrator, "_http_adapter", lambda provider: MockHttpAdapter())

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
        disable_response = client.patch(
            "/admin/providers/codex/models/gpt-5.4",
            json={"enabled": False},
            headers={"x-admin-secret": "change-me"},
        )
        assert disable_response.status_code == 200

        response = client.post(
            "/admin/test-chat",
            json={
                "model": "codex:gpt-5.4",
                "messages": [{"role": "user", "content": "ping"}],
            },
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "model is disabled"


def test_admin_test_chat_can_stream_sse_chunks(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setattr(chat_orchestrator, "_http_adapter", lambda provider: MockHttpAdapter())

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

        with client.stream(
            "POST",
            "/admin/test-chat",
            json={
                "model": "codex:gpt-5.4",
                "messages": [{"role": "user", "content": "ping"}],
                "stream": True,
            },
            headers={"x-admin-secret": "change-me"},
        ) as response:
            payload = "".join(response.iter_text())

    assert response.status_code == 200
    assert "mocked-" in payload
    assert "http-response" in payload
    assert "[DONE]" in payload


def test_admin_test_chat_returns_provider_error_without_500(tmp_path, monkeypatch) -> None:
    class FailingHttpAdapter:
        async def chat(self, request: ChatRequest) -> dict[str, object]:
            upstream_request = httpx.Request("POST", "http://provider.invalid/v1/chat/completions")
            upstream_response = httpx.Response(
                400,
                json={"error": {"message": "unknown model"}},
                request=upstream_request,
            )
            raise httpx.HTTPStatusError(
                "upstream rejected model",
                request=upstream_request,
                response=upstream_response,
            )

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setattr(chat_orchestrator, "_http_adapter", lambda provider: FailingHttpAdapter())

    with TestClient(create_app(), raise_server_exceptions=False) as client:
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

        response = client.post(
            "/admin/test-chat",
            json={
                "model": "codex:gpt-5.4",
                "messages": [{"role": "user", "content": "ping"}],
            },
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "provider returned 400: unknown model"


def test_admin_stream_test_chat_returns_provider_error_before_first_chunk(tmp_path, monkeypatch) -> None:
    class FailingStreamHttpAdapter:
        async def stream_chat(self, request: ChatRequest):
            upstream_request = httpx.Request("POST", "http://provider.invalid/v1/chat/completions")
            upstream_response = httpx.Response(
                429,
                json={"detail": "rate limited"},
                request=upstream_request,
            )
            raise httpx.HTTPStatusError(
                "upstream rate limited",
                request=upstream_request,
                response=upstream_response,
            )
            yield ""

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setattr(chat_orchestrator, "_http_adapter", lambda provider: FailingStreamHttpAdapter())

    with TestClient(create_app(), raise_server_exceptions=False) as client:
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

        response = client.post(
            "/admin/test-chat",
            json={
                "model": "codex:gpt-5.4",
                "messages": [{"role": "user", "content": "ping"}],
                "stream": True,
            },
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "provider returned 429: rate limited"
