from fastapi.testclient import TestClient

from app.api.admin import get_admin_hermes_runner
from app.main import create_app


class FakeRunner:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    async def enqueue(self, task_id: str) -> None:
        self.enqueued.append(task_id)


def _app_with_runner(runner: FakeRunner):
    app = create_app()
    app.dependency_overrides[get_admin_hermes_runner] = lambda: runner
    return app


def _create_account_key_and_pricing(client: TestClient) -> tuple[int, int]:
    account_response = client.post(
        "/admin/accounts",
        json={"name": "admin-hermes-account", "is_admin": True},
        headers={"x-admin-secret": "change-me"},
    )
    assert account_response.status_code == 201
    account_id = account_response.json()["id"]
    model_access_response = client.put(
        f"/admin/accounts/{account_id}/model-access",
        json={"platform_model_access_mode": "all", "allowed_model_ids": ["hermes:hermes-agent"]},
        headers={"x-admin-secret": "change-me"},
    )
    assert model_access_response.status_code == 200
    credit_response = client.post(
        f"/admin/accounts/{account_id}/credits/adjust",
        json={"credits_delta": 5000, "notes": "hermes admin test"},
        headers={"x-admin-secret": "change-me"},
    )
    assert credit_response.status_code == 200
    key_response = client.post(
        "/admin/api-keys",
        json={"account_id": account_id, "name": "admin-hermes-key"},
        headers={"x-admin-secret": "change-me"},
    )
    assert key_response.status_code == 201
    return account_id, key_response.json()["id"]


def test_admin_can_create_list_cancel_and_replay_hermes_task(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.setenv("HERMES_API_KEY", "test-hermes-key")
    monkeypatch.setenv("HERMES_MODEL", "hermes-agent")
    runner = FakeRunner()
    app = _app_with_runner(runner)

    try:
        with TestClient(app) as client:
            account_id, api_key_id = _create_account_key_and_pricing(client)
            overview_response = client.get("/admin/hermes/overview", headers={"x-admin-secret": "change-me"})
            create_response = client.post(
                "/admin/hermes/tasks",
                json={
                    "account_id": account_id,
                    "api_key_id": api_key_id,
                    "input": "run from admin",
                    "metadata": {"case": "admin"},
                },
                headers={"x-admin-secret": "change-me"},
            )
            task_id = create_response.json()["id"]
            list_response = client.get("/admin/hermes/tasks", headers={"x-admin-secret": "change-me"})
            get_response = client.get(f"/admin/hermes/tasks/{task_id}", headers={"x-admin-secret": "change-me"})
            cancel_response = client.post(
                f"/admin/hermes/tasks/{task_id}/cancel",
                headers={"x-admin-secret": "change-me"},
            )
            events_response = client.get(
                f"/admin/hermes/tasks/{task_id}/events",
                headers={"x-admin-secret": "change-me"},
            )
    finally:
        app.dependency_overrides.clear()

    assert overview_response.status_code == 200
    assert overview_response.json()["enabled"] is True
    assert overview_response.json()["model_id"] == "hermes:hermes-agent"
    assert create_response.status_code == 202
    assert create_response.json()["status"] == "queued"
    assert create_response.json()["account_id"] == account_id
    assert create_response.json()["api_key_id"] == api_key_id
    assert runner.enqueued == [task_id]
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["id"] == task_id
    assert get_response.status_code == 200
    assert get_response.json()["input_text"] == "run from admin"
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancel_requested"
    assert events_response.status_code == 200
    assert events_response.json()[0]["event_type"] == "task.status"
    assert events_response.json()[0]["payload"] == {"status": "cancel_requested"}


def test_admin_hermes_create_requires_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("HERMES_ENABLED", "false")

    with TestClient(create_app()) as client:
        account_response = client.post(
            "/admin/accounts",
            json={"name": "disabled-hermes-account"},
            headers={"x-admin-secret": "change-me"},
        )
        key_response = client.post(
            "/admin/api-keys",
            json={"account_id": account_response.json()["id"], "name": "disabled-hermes-key"},
            headers={"x-admin-secret": "change-me"},
        )
        response = client.post(
            "/admin/hermes/tasks",
            json={
                "account_id": account_response.json()["id"],
                "api_key_id": key_response.json()["id"],
                "input": "run from admin",
            },
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Hermes task API is disabled"}
