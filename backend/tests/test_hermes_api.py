from fastapi.testclient import TestClient

from app.api.hermes import get_hermes_runner
from app.main import create_app


class FakeRunner:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    async def enqueue(self, task_id: str) -> None:
        self.enqueued.append(task_id)


def _create_account_and_key(client: TestClient) -> str:
    account_response = client.post(
        "/admin/accounts",
        json={"name": "hermes-account"},
        headers={"x-admin-secret": "change-me"},
    )
    assert account_response.status_code == 201
    key_response = client.post(
        "/admin/api-keys",
        json={"account_id": account_response.json()["id"], "name": "hermes-key"},
        headers={"x-admin-secret": "change-me"},
    )
    assert key_response.status_code == 201
    return key_response.json()["api_key"]


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


def test_hermes_task_api_requires_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    monkeypatch.setenv("HERMES_ENABLED", "false")

    with TestClient(create_app()) as client:
        api_key = _create_account_and_key(client)
        response = client.post(
            "/v1/hermes/tasks",
            json={"input": "run long job"},
            headers={"authorization": f"Bearer {api_key}"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Hermes task API is disabled"}
