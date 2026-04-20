import sqlite3

from fastapi.testclient import TestClient

from app.main import create_app


def test_startup_backfills_auth_tables_and_columns(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "gateway.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")

    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) UNIQUE NOT NULL,
                status VARCHAR(32) NOT NULL,
                notes TEXT
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(create_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200

    connection = sqlite3.connect(database_path)
    try:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(accounts)").fetchall()
        }
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        connection.close()

    assert "password_hash" in columns
    assert "oauth_provider" in columns
    assert "auth_sessions" in tables
