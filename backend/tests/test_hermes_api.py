from fastapi.testclient import TestClient

from app.api.hermes import get_hermes_runner
from app.main import create_app


class FakeRunner:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    async def enqueue(self, task_id: str) -> None:
        self.enqueued.append(task_id)


def _create_account_and_key_pair(
    client: TestClient,
    name: str = "hermes-account",
    credits: float = 5000,
    *,
    is_admin: bool = True,
    grant_hermes: bool = True,
) -> tuple[int, str]:
    account_response = client.post(
        "/admin/accounts",
        json={"name": name, "is_admin": is_admin},
        headers={"x-admin-secret": "change-me"},
    )
    assert account_response.status_code == 201
    account_id = account_response.json()["id"]
    credit_response = client.post(
        f"/admin/accounts/{account_id}/credits/adjust",
        json={"credits_delta": credits, "notes": "test credits"},
        headers={"x-admin-secret": "change-me"},
    )
    assert credit_response.status_code == 200
    key_response = client.post(
        "/admin/api-keys",
        json={"account_id": account_id, "name": "hermes-key"},
        headers={"x-admin-secret": "change-me"},
    )
    assert key_response.status_code == 201
    if grant_hermes:
        model_access_response = client.put(
            f"/admin/accounts/{account_id}/model-access",
            json={"platform_model_access_mode": "all", "allowed_model_ids": ["hermes:hermes-agent"]},
            headers={"x-admin-secret": "change-me"},
        )
        assert model_access_response.status_code == 200
    return account_id, key_response.json()["api_key"]


def _create_account_and_key(
    client: TestClient,
    name: str = "hermes-account",
    credits: float = 5000,
    *,
    is_admin: bool = True,
    grant_hermes: bool = True,
) -> str:
    _, api_key = _create_account_and_key_pair(
        client,
        name,
        credits,
        is_admin=is_admin,
        grant_hermes=grant_hermes,
    )
    return api_key


def _app_with_runner(runner: FakeRunner):
    app = create_app()
    app.dependency_overrides[get_hermes_runner] = lambda: runner
    return app


def test_create_and_get_hermes_task(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.setenv("HERMES_API_KEY", "test-hermes-key")

    runner = FakeRunner()
    app = _app_with_runner(runner)
    try:
        with TestClient(app) as client:
            api_key = _create_account_and_key(client)
            create_response = client.post(
                "/v1/hermes/tasks",
                json={"input": "run long job", "metadata": {"source": "test"}},
                headers={"authorization": f"Bearer {api_key}"},
            )
            assert create_response.status_code == 202
            task_id = create_response.json()["id"]
            get_response = client.get(
                f"/v1/hermes/tasks/{task_id}",
                headers={"authorization": f"Bearer {api_key}"},
            )
            list_response = client.get(
                "/v1/hermes/tasks",
                headers={"authorization": f"Bearer {api_key}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert runner.enqueued == [task_id]
    assert create_response.json()["status"] == "queued"
    assert get_response.status_code == 200
    assert get_response.json()["id"] == task_id
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1


def test_create_task_enqueues_runner(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.setenv("HERMES_API_KEY", "test-hermes-key")

    runner = FakeRunner()
    app = _app_with_runner(runner)
    try:
        with TestClient(app) as client:
            api_key = _create_account_and_key(client)
            response = client.post(
                "/v1/hermes/tasks",
                json={"input": "run long job"},
                headers={"authorization": f"Bearer {api_key}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert runner.enqueued == [response.json()["id"]]


def test_hermes_runner_starts_with_app(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.setenv("HERMES_API_KEY", "test-hermes-key")
    monkeypatch.setenv("HERMES_MAX_CONCURRENT_TASKS", "1")

    app = create_app()
    with TestClient(app):
        runner = app.state.hermes_task_runner
        assert runner.max_concurrent_tasks == 1
        assert len(runner._workers) == 1

    assert app.state.hermes_task_runner._workers == []


def test_cancel_hermes_task(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.setenv("HERMES_API_KEY", "test-hermes-key")

    app = _app_with_runner(FakeRunner())
    try:
        with TestClient(app) as client:
            api_key = _create_account_and_key(client)
            create_response = client.post(
                "/v1/hermes/tasks",
                json={"input": "cancel me"},
                headers={"authorization": f"Bearer {api_key}"},
            )
            assert create_response.status_code == 202
            cancel_response = client.post(
                f"/v1/hermes/tasks/{create_response.json()['id']}/cancel",
                headers={"authorization": f"Bearer {api_key}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancel_requested"


def test_hermes_model_requires_admin_account_and_explicit_grant(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.setenv("HERMES_API_KEY", "test-hermes-key")
    monkeypatch.setenv("HERMES_MODEL", "hermes-agent")

    app = _app_with_runner(FakeRunner())
    try:
        with TestClient(app) as client:
            non_admin_account_id, non_admin_api_key = _create_account_and_key_pair(
                client,
                name="non-admin-hermes-account",
                is_admin=False,
                grant_hermes=False,
            )
            default_models_response = client.get(
                "/v1/models",
                headers={"authorization": f"Bearer {non_admin_api_key}"},
            )
            grant_to_non_admin_response = client.put(
                f"/admin/accounts/{non_admin_account_id}/model-access",
                json={"platform_model_access_mode": "all", "allowed_model_ids": ["hermes:hermes-agent"]},
                headers={"x-admin-secret": "change-me"},
            )
            non_admin_models_response = client.get(
                "/v1/models",
                headers={"authorization": f"Bearer {non_admin_api_key}"},
            )
            non_admin_task_response = client.post(
                "/v1/hermes/tasks",
                json={"input": "must not run"},
                headers={"authorization": f"Bearer {non_admin_api_key}"},
            )

            admin_account_id, admin_api_key = _create_account_and_key_pair(
                client,
                name="admin-hermes-account",
                is_admin=True,
                grant_hermes=False,
            )
            admin_before_grant_response = client.get(
                "/v1/models",
                headers={"authorization": f"Bearer {admin_api_key}"},
            )
            grant_to_admin_response = client.put(
                f"/admin/accounts/{admin_account_id}/model-access",
                json={"platform_model_access_mode": "all", "allowed_model_ids": ["hermes:hermes-agent"]},
                headers={"x-admin-secret": "change-me"},
            )
            admin_models_response = client.get(
                "/v1/models",
                headers={"authorization": f"Bearer {admin_api_key}"},
            )
            admin_task_response = client.post(
                "/v1/hermes/tasks",
                json={"input": "run long job"},
                headers={"authorization": f"Bearer {admin_api_key}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert default_models_response.status_code == 200
    assert "hermes:hermes-agent" not in {item["id"] for item in default_models_response.json()["data"]}
    assert grant_to_non_admin_response.status_code == 422
    assert grant_to_non_admin_response.json() == {
        "detail": "admin permission required for platform model: hermes:hermes-agent"
    }
    assert "hermes:hermes-agent" not in {item["id"] for item in non_admin_models_response.json()["data"]}
    assert non_admin_task_response.status_code == 404
    assert non_admin_task_response.json() == {"detail": "Hermes model is not available"}

    assert admin_before_grant_response.status_code == 200
    assert "hermes:hermes-agent" not in {item["id"] for item in admin_before_grant_response.json()["data"]}
    assert grant_to_admin_response.status_code == 200
    assert grant_to_admin_response.json()["platform_model_access_mode"] == "all"
    assert grant_to_admin_response.json()["allowed_model_ids"] == ["hermes:hermes-agent"]
    assert "hermes:hermes-agent" in {item["id"] for item in admin_models_response.json()["data"]}
    assert admin_task_response.status_code == 202


def test_hermes_task_create_charges_start_fee_without_model_pricing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.setenv("HERMES_API_KEY", "test-hermes-key")

    app = _app_with_runner(FakeRunner())
    try:
        with TestClient(app) as client:
            account_id, api_key = _create_account_and_key_pair(client, credits=11)
            response = client.post(
                "/v1/hermes/tasks",
                json={"input": "run long job"},
                headers={"authorization": f"Bearer {api_key}"},
            )
            accounts_response = client.get("/admin/accounts", headers={"x-admin-secret": "change-me"})
            usage_response = client.get("/admin/usage/records", headers={"x-admin-secret": "change-me"})
            ledger_response = client.get(
                f"/admin/accounts/{account_id}/credits/ledger",
                headers={"x-admin-secret": "change-me"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    account_row = next(item for item in accounts_response.json() if item["id"] == account_id)
    assert account_row["credit_balance"] == 1
    assert usage_response.json()["items"][0]["provider_name"] == "hermes"
    assert usage_response.json()["items"][0]["model_id"] == "hermes:hermes-agent"
    assert usage_response.json()["items"][0]["credits_charged"] == 10
    assert usage_response.json()["items"][0]["token_source"] == "hermes_start_fee"
    assert ledger_response.json()["items"][0]["entry_type"] == "hermes_task_start"
    assert ledger_response.json()["items"][0]["credits_delta"] == -10


def test_hermes_task_create_requires_start_fee_balance(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.setenv("HERMES_API_KEY", "test-hermes-key")

    app = _app_with_runner(FakeRunner())
    try:
        with TestClient(app) as client:
            api_key = _create_account_and_key(client, credits=9)
            response = client.post(
                "/v1/hermes/tasks",
                json={"input": "run long job"},
                headers={"authorization": f"Bearer {api_key}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 402
    assert response.json() == {"detail": "余额不足，请充值"}


def test_hermes_task_api_requires_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("HERMES_ENABLED", "false")

    with TestClient(create_app()) as client:
        api_key = _create_account_and_key(client, grant_hermes=False)
        response = client.post(
            "/v1/hermes/tasks",
            json={"input": "run long job"},
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Hermes task API is disabled"}
