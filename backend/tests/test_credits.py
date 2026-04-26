from fastapi.testclient import TestClient

from app.adapters.http.base import MockHttpAdapter
from app.api import openai as openai_api
from app.main import create_app


def _create_account(client: TestClient, name: str) -> int:
    response = client.post(
        "/admin/accounts",
        json={"name": name},
        headers={"x-admin-secret": "change-me"},
    )
    return response.json()["id"]


def _create_api_key(client: TestClient, account_id: int, name: str) -> str:
    response = client.post(
        "/admin/api-keys",
        json={"account_id": account_id, "name": name},
        headers={"x-admin-secret": "change-me"},
    )
    return response.json()["api_key"]


def test_admin_can_adjust_account_credits_and_list_ledger(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        account_id = _create_account(client, "credit-account")
        adjust_response = client.post(
            f"/admin/accounts/{account_id}/credits/adjust",
            json={"credits_delta": 1500.25, "notes": "bootstrap credits"},
            headers={"x-admin-secret": "change-me"},
        )
        accounts_response = client.get("/admin/accounts", headers={"x-admin-secret": "change-me"})
        ledger_response = client.get(
            f"/admin/accounts/{account_id}/credits/ledger",
            headers={"x-admin-secret": "change-me"},
        )

    assert adjust_response.status_code == 200
    assert adjust_response.json()["credit_balance"] == 1500.25
    assert accounts_response.json()[0]["credit_balance"] == 1500.25
    assert ledger_response.status_code == 200
    ledger_payload = ledger_response.json()
    assert ledger_payload["total"] == 1
    assert ledger_payload["limit"] == 25
    assert ledger_payload["offset"] == 0
    assert ledger_payload["items"][0]["entry_type"] == "manual_adjustment"
    assert ledger_payload["items"][0]["credits_delta"] == 1500.25


def test_admin_account_credit_ledger_supports_offset_pagination(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        account_id = _create_account(client, "paged-ledger-account")
        for amount, notes in ((10, "first"), (20, "second"), (30, "third")):
            response = client.post(
                f"/admin/accounts/{account_id}/credits/adjust",
                json={"credits_delta": amount, "notes": notes},
                headers={"x-admin-secret": "change-me"},
            )
            assert response.status_code == 200
        ledger_response = client.get(
            f"/admin/accounts/{account_id}/credits/ledger?limit=1&offset=1",
            headers={"x-admin-secret": "change-me"},
        )

    assert ledger_response.status_code == 200
    payload = ledger_response.json()
    assert payload["total"] == 3
    assert payload["limit"] == 1
    assert payload["offset"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["notes"] == "second"
    assert payload["items"][0]["credits_delta"] == 20


def test_chat_rejects_requests_when_account_has_no_credits(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        account_id = _create_account(client, "empty-credit-account")
        api_key = _create_api_key(client, account_id, "empty-credit-key")
        client.post(
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

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "codex:gpt-5.4",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert response.status_code == 402
    assert response.json() == {"detail": "余额不足，请充值"}


def test_chat_rejects_requests_when_decimal_balance_is_insufficient(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        account_id = _create_account(client, "decimal-credit-account")
        client.post(
            f"/admin/accounts/{account_id}/credits/adjust",
            json={"credits_delta": 0.02, "notes": "small balance"},
            headers={"x-admin-secret": "change-me"},
        )
        api_key = _create_api_key(client, account_id, "decimal-credit-key")
        client.post(
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

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "codex:gpt-5.4",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
                "max_tokens": 16,
            },
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert response.status_code == 402
    assert response.json() == {"detail": "余额不足，请充值"}


def test_successful_chat_deducts_credits_and_records_ledger(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setattr(openai_api.orchestrator, "_http_adapter", lambda provider: MockHttpAdapter())

    with TestClient(create_app()) as client:
        account_id = _create_account(client, "paid-credit-account")
        client.post(
            f"/admin/accounts/{account_id}/credits/adjust",
            json={"credits_delta": 1000.25, "notes": "bootstrap credits"},
            headers={"x-admin-secret": "change-me"},
        )
        api_key = _create_api_key(client, account_id, "paid-credit-key")
        client.post(
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

        chat_response = client.post(
            "/v1/chat/completions",
            json={
                "model": "codex:gpt-5.4",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
                "max_tokens": 16,
            },
            headers={"authorization": f"Bearer {api_key}"},
        )
        accounts_response = client.get("/admin/accounts", headers={"x-admin-secret": "change-me"})
        ledger_response = client.get(
            f"/admin/accounts/{account_id}/credits/ledger",
            headers={"x-admin-secret": "change-me"},
        )

    assert chat_response.status_code == 200
    assert accounts_response.status_code == 200
    account_payload = accounts_response.json()[0]
    assert account_payload["credit_balance"] == 1000.19
    inference_entry = next(
        entry for entry in ledger_response.json()["items"] if entry["entry_type"] == "model_inference"
    )
    assert inference_entry["model_id"] == "codex:gpt-5.4"
    assert inference_entry["credits_delta"] == -0.06
    assert inference_entry["balance_after"] == 1000.19
    assert inference_entry["pricing_source"] == "official_snapshot"
