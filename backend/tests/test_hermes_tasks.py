import pytest
from sqlalchemy import text

from app.core.db import get_engine, get_session_factory
from app.core.models import AccountRecord, ApiKeyRecord, Base
from app.core.settings import Settings
from app.services.hermes_tasks import (
    HERMES_STATUS_QUEUED,
    HermesTaskCreate,
    append_hermes_task_event,
    create_hermes_task,
    get_hermes_task_for_account,
    list_hermes_task_events,
    list_hermes_tasks_for_account,
)


def test_hermes_settings_read_environment(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_ENABLED", "true")
    monkeypatch.setenv("HERMES_API_BASE", "http://127.0.0.1:8642/v1")
    monkeypatch.setenv("HERMES_API_KEY", "secret")
    monkeypatch.setenv("HERMES_MODEL", "hermes-agent")
    monkeypatch.setenv("HERMES_MAX_CONCURRENT_TASKS", "3")

    settings = Settings()

    assert settings.hermes_enabled is True
    assert settings.hermes_api_base == "http://127.0.0.1:8642/v1"
    assert settings.hermes_api_key == "secret"
    assert settings.hermes_model == "hermes-agent"
    assert settings.hermes_max_concurrent_tasks == 3


def test_hermes_settings_discovers_api_key_from_home_env(tmp_path, monkeypatch) -> None:
    hermes_env = tmp_path / ".hermes" / ".env"
    hermes_env.parent.mkdir()
    hermes_env.write_text("API_SERVER_KEY='server-key'\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.delenv("HERMES_ENABLED", raising=False)
    monkeypatch.delenv("HERMES_ENV_FILE", raising=False)

    settings = Settings(_env_file=None)

    assert settings.hermes_enabled is True
    assert settings.hermes_api_key == "server-key"


def test_hermes_settings_discovers_api_key_from_configured_env_file(tmp_path, monkeypatch) -> None:
    hermes_env = tmp_path / "hermes.env"
    hermes_env.write_text("export API_SERVER_KEY=\"configured-key\"\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_ENV_FILE", str(hermes_env))
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.delenv("HERMES_ENABLED", raising=False)

    settings = Settings(_env_file=None)

    assert settings.hermes_enabled is True
    assert settings.hermes_api_key == "configured-key"


def test_hermes_settings_prefers_explicit_api_key(tmp_path, monkeypatch) -> None:
    hermes_env = tmp_path / ".hermes" / ".env"
    hermes_env.parent.mkdir()
    hermes_env.write_text("API_SERVER_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_API_KEY", "explicit-key")

    settings = Settings(_env_file=None)

    assert settings.hermes_api_key == "explicit-key"


def test_hermes_settings_can_disable_env_discovery(tmp_path, monkeypatch) -> None:
    hermes_env = tmp_path / ".hermes" / ".env"
    hermes_env.parent.mkdir()
    hermes_env.write_text("API_SERVER_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.setenv("HERMES_AUTO_DISCOVER_ENV", "false")

    settings = Settings(_env_file=None)

    assert settings.hermes_enabled is False
    assert settings.hermes_api_key is None


def test_hermes_settings_respects_explicit_disabled_flag(tmp_path, monkeypatch) -> None:
    hermes_env = tmp_path / ".hermes" / ".env"
    hermes_env.parent.mkdir()
    hermes_env.write_text("API_SERVER_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.setenv("HERMES_ENABLED", "false")

    settings = Settings(_env_file=None)

    assert settings.hermes_enabled is False
    assert settings.hermes_api_key is None


@pytest.mark.asyncio
async def test_hermes_tables_are_created(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    engine = get_engine(database_url)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        tables = {
            row[0]
            for row in (
                await connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                )
            ).all()
        }
        task_columns = {
            row[1]
            for row in (
                await connection.execute(text("PRAGMA table_info(hermes_tasks)"))
            ).all()
        }
        event_columns = {
            row[1]
            for row in (
                await connection.execute(text("PRAGMA table_info(hermes_task_events)"))
            ).all()
        }

    await engine.dispose()

    assert "hermes_tasks" in tables
    assert "hermes_task_events" in tables
    assert {"id", "account_id", "api_key_id", "status", "input_text", "output_text"} <= task_columns
    assert {"task_id", "seq", "event_type", "payload_json"} <= event_columns


@pytest.mark.asyncio
async def test_create_task_and_replay_events(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    engine = get_engine(database_url)
    session_factory = get_session_factory(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        account = AccountRecord(name="acct", credit_balance=100)
        session.add(account)
        await session.flush()
        api_key = ApiKeyRecord(account_id=account.id, name="key", key_prefix="sk-test", secret_hash="hash")
        session.add(api_key)
        await session.commit()

        task = await create_hermes_task(
            session,
            account=account,
            api_key=api_key,
            payload=HermesTaskCreate(input_text="hello", metadata={"source": "test"}),
        )
        await append_hermes_task_event(
            session,
            task_id=task.id,
            event_type="response.output_text.delta",
            payload={"delta": "hi"},
        )
        await session.commit()

        loaded = await get_hermes_task_for_account(session, task.id, account.id)
        events = await list_hermes_task_events(session, task.id, after_seq=0)
        page = await list_hermes_tasks_for_account(session, account.id, limit=10, offset=0, status=None)

    await engine.dispose()

    assert loaded is not None
    assert loaded.status == HERMES_STATUS_QUEUED
    assert loaded.conversation == f"acct:{account.id}:default"
    assert events[0].seq == 1
    assert events[0].event_type == "response.output_text.delta"
    assert page["total"] == 1
    assert page["items"][0].id == task.id
