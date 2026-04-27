import pytest
from sqlalchemy import text

from app.core.db import get_engine
from app.core.models import Base
from app.core.settings import Settings


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
