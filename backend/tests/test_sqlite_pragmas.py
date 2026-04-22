from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.db import get_engine


@pytest.mark.asyncio
async def test_sqlite_engine_applies_expected_pragmas(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}"
    engine = get_engine(database_url)

    async with engine.connect() as connection:
        journal_mode = await connection.scalar(text("PRAGMA journal_mode"))
        foreign_keys = await connection.scalar(text("PRAGMA foreign_keys"))
        busy_timeout = await connection.scalar(text("PRAGMA busy_timeout"))

    assert str(journal_mode).lower() == "wal"
    assert int(foreign_keys) == 1
    assert int(busy_timeout) >= 5000
