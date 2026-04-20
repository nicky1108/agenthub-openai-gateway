from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.engine import Connection

from app.api.admin import router as admin_router
from app.api.health import router as health_router
from app.api.openai import router as openai_router
from app.core.db import get_engine, get_session_factory
from app.core.models import Base, ProviderRecord
from app.core.settings import Settings
from app.discovery.service import ProviderDiscoveryService
from sqlalchemy import select


def backfill_sqlite_provider_capability_columns(connection: Connection) -> None:
    if connection.dialect.name != "sqlite":
        return

    table_rows = connection.exec_driver_sql("PRAGMA table_info(providers)").mappings().all()
    column_names = {row["name"] for row in table_rows}
    if not column_names:
        return

    if "chat_capable" not in column_names:
        connection.exec_driver_sql(
            "ALTER TABLE providers ADD COLUMN chat_capable BOOLEAN NOT NULL DEFAULT 1"
        )
    if "stream_capable" not in column_names:
        connection.exec_driver_sql(
            "ALTER TABLE providers ADD COLUMN stream_capable BOOLEAN NOT NULL DEFAULT 1"
        )
    if "exposed_model" not in column_names:
        connection.exec_driver_sql(
            "ALTER TABLE providers ADD COLUMN exposed_model VARCHAR(200) NOT NULL DEFAULT 'default'"
        )
    if "http_base_url" not in column_names:
        connection.exec_driver_sql(
            "ALTER TABLE providers ADD COLUMN http_base_url VARCHAR(500)"
        )
    if "http_api_key" not in column_names:
        connection.exec_driver_sql(
            "ALTER TABLE providers ADD COLUMN http_api_key VARCHAR(500)"
        )
    if "http_headers_json" not in column_names:
        connection.exec_driver_sql(
            "ALTER TABLE providers ADD COLUMN http_headers_json TEXT NOT NULL DEFAULT '{}'"
        )
    if "cli_command" not in column_names:
        connection.exec_driver_sql(
            "ALTER TABLE providers ADD COLUMN cli_command VARCHAR(500)"
        )
    if "cli_args_json" not in column_names:
        connection.exec_driver_sql(
            "ALTER TABLE providers ADD COLUMN cli_args_json TEXT NOT NULL DEFAULT '[]'"
        )
    if "cli_env_json" not in column_names:
        connection.exec_driver_sql(
            "ALTER TABLE providers ADD COLUMN cli_env_json TEXT NOT NULL DEFAULT '{}'"
        )
    if "cli_cwd" not in column_names:
        connection.exec_driver_sql(
            "ALTER TABLE providers ADD COLUMN cli_cwd VARCHAR(500)"
        )


def backfill_sqlite_account_auth_columns(connection: Connection) -> None:
    if connection.dialect.name != "sqlite":
        return

    table_rows = connection.exec_driver_sql("PRAGMA table_info(accounts)").mappings().all()
    column_names = {row["name"] for row in table_rows}
    if not column_names:
        return

    if "email" not in column_names:
        connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN email VARCHAR(320)")
    if "password_hash" not in column_names:
        connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN password_hash VARCHAR(255)")
    if "oauth_provider" not in column_names:
        connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN oauth_provider VARCHAR(32)")
    if "oauth_subject" not in column_names:
        connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN oauth_subject VARCHAR(255)")
    if "created_at" not in column_names:
        connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN created_at DATETIME")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = Settings()
    engine = get_engine(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(backfill_sqlite_provider_capability_columns)
        await connection.run_sync(backfill_sqlite_account_auth_columns)
    session_factory = get_session_factory(settings.database_url)
    discovery = ProviderDiscoveryService()
    async with session_factory() as session:
        providers = await session.scalars(
            select(ProviderRecord).where(
                (ProviderRecord.name == "codex") | (ProviderRecord.name == "gemini")
            )
        )
        for provider in providers:
            await discovery.sync_provider_models(session, provider)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="AgentHub OpenAI Gateway", lifespan=lifespan)
    app.include_router(admin_router)
    app.include_router(health_router)
    app.include_router(openai_router)
    return app


app = create_app()
