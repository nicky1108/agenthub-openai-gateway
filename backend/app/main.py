from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.engine import Connection

from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.health import router as health_router
from app.api.hermes import router as hermes_router
from app.api.internal_public_gateway import router as internal_public_gateway_router
from app.api.openai import orchestrator as openai_orchestrator
from app.api.openai import router as openai_router
from app.api.portal import router as portal_router
from app.api.user import router as user_router
from app.core.db import get_engine, get_session_factory
from app.core.models import Base, ProviderRecord
from app.core.settings import Settings, validate_secure_runtime_config
from app.discovery.service import ProviderDiscoveryService
from app.pricing.service import OfficialPricingService
from app.runtime.hermes_task_runner import HermesTaskRunner
from app.runtime.logging import log_gateway_event
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
    if "public_account_id" not in column_names:
        connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN public_account_id VARCHAR(128)")
    if "public_workspace_id" not in column_names:
        connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN public_workspace_id VARCHAR(128)")
    if "is_admin" not in column_names:
        connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0")
    if "created_at" not in column_names:
        connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN created_at DATETIME")
    if "credit_balance" not in column_names:
        connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN credit_balance FLOAT NOT NULL DEFAULT 0")
    if "platform_model_access_mode" not in column_names:
        connection.exec_driver_sql(
            "ALTER TABLE accounts ADD COLUMN platform_model_access_mode VARCHAR(32) NOT NULL DEFAULT 'all'"
        )

    index_rows = connection.exec_driver_sql("PRAGMA index_list(accounts)").mappings().all()
    has_unique_email_index = False
    for row in index_rows:
        if not row["unique"]:
            continue
        index_columns = connection.exec_driver_sql(
            f"PRAGMA index_info('{row['name']}')"
        ).mappings().all()
        if any(column["name"] == "email" for column in index_columns):
            has_unique_email_index = True
            break

    if not has_unique_email_index:
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_accounts_email ON accounts(email)"
        )

    connection.exec_driver_sql(
        "UPDATE accounts SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
    )


def backfill_sqlite_usage_billing_columns(connection: Connection) -> None:
    if connection.dialect.name != "sqlite":
        return

    table_rows = connection.exec_driver_sql("PRAGMA table_info(usage_records)").mappings().all()
    column_names = {row["name"] for row in table_rows}
    if not column_names:
        return

    if "input_tokens" not in column_names:
        connection.exec_driver_sql("ALTER TABLE usage_records ADD COLUMN input_tokens INTEGER")
    if "output_tokens" not in column_names:
        connection.exec_driver_sql("ALTER TABLE usage_records ADD COLUMN output_tokens INTEGER")
    if "cached_input_tokens" not in column_names:
        connection.exec_driver_sql("ALTER TABLE usage_records ADD COLUMN cached_input_tokens INTEGER")
    if "usd_amount" not in column_names:
        connection.exec_driver_sql("ALTER TABLE usage_records ADD COLUMN usd_amount FLOAT")
    if "credits_charged" not in column_names:
        connection.exec_driver_sql("ALTER TABLE usage_records ADD COLUMN credits_charged FLOAT")
    if "pricing_source" not in column_names:
        connection.exec_driver_sql("ALTER TABLE usage_records ADD COLUMN pricing_source VARCHAR(32)")
    if "token_source" not in column_names:
        connection.exec_driver_sql("ALTER TABLE usage_records ADD COLUMN token_source VARCHAR(32)")


def backfill_sqlite_api_key_public_columns(connection: Connection) -> None:
    if connection.dialect.name != "sqlite":
        return

    table_rows = connection.exec_driver_sql("PRAGMA table_info(api_keys)").mappings().all()
    column_names = {row["name"] for row in table_rows}
    if not column_names:
        return

    if "public_api_key_id" not in column_names:
        connection.exec_driver_sql("ALTER TABLE api_keys ADD COLUMN public_api_key_id VARCHAR(128)")


def backfill_sqlite_user_provider_columns(connection: Connection) -> None:
    if connection.dialect.name != "sqlite":
        return

    table_rows = connection.exec_driver_sql("PRAGMA table_info(user_providers)").mappings().all()
    column_names = {row["name"] for row in table_rows}
    if not column_names:
        return

    if "protocol" not in column_names:
        connection.exec_driver_sql(
            "ALTER TABLE user_providers ADD COLUMN protocol VARCHAR(32) NOT NULL DEFAULT 'openai'"
        )
    if "secret_ref" not in column_names:
        connection.exec_driver_sql("ALTER TABLE user_providers ADD COLUMN secret_ref VARCHAR(255) NOT NULL DEFAULT ''")
    if "last_probe_at" not in column_names:
        connection.exec_driver_sql("ALTER TABLE user_providers ADD COLUMN last_probe_at DATETIME")
    if "last_probe_ok" not in column_names:
        connection.exec_driver_sql("ALTER TABLE user_providers ADD COLUMN last_probe_ok BOOLEAN")
    if "last_probe_model" not in column_names:
        connection.exec_driver_sql("ALTER TABLE user_providers ADD COLUMN last_probe_model VARCHAR(300)")
    if "last_probe_detail" not in column_names:
        connection.exec_driver_sql("ALTER TABLE user_providers ADD COLUMN last_probe_detail VARCHAR(500)")
    if "last_detected_models_json" not in column_names:
        connection.exec_driver_sql(
            "ALTER TABLE user_providers ADD COLUMN last_detected_models_json TEXT NOT NULL DEFAULT '[]'"
        )


def backfill_sqlite_model_pricing_columns(connection: Connection) -> None:
    if connection.dialect.name != "sqlite":
        return

    table_rows = connection.exec_driver_sql("PRAGMA table_info(model_pricing)").mappings().all()
    column_names = {row["name"] for row in table_rows}
    if not column_names:
        return

    if "source_kind" not in column_names:
        connection.exec_driver_sql(
            "ALTER TABLE model_pricing ADD COLUMN source_kind VARCHAR(32) NOT NULL DEFAULT 'official_snapshot'"
        )


def backfill_sqlite_hermes_task_billing_columns(connection: Connection) -> None:
    if connection.dialect.name != "sqlite":
        return

    table_rows = connection.exec_driver_sql("PRAGMA table_info(hermes_tasks)").mappings().all()
    column_names = {row["name"] for row in table_rows}
    if not column_names:
        return

    if "start_usage_record_id" not in column_names:
        connection.exec_driver_sql("ALTER TABLE hermes_tasks ADD COLUMN start_usage_record_id INTEGER")
    if "runtime_usage_record_id" not in column_names:
        connection.exec_driver_sql("ALTER TABLE hermes_tasks ADD COLUMN runtime_usage_record_id INTEGER")
    if "runtime_billable_minutes" not in column_names:
        connection.exec_driver_sql("ALTER TABLE hermes_tasks ADD COLUMN runtime_billable_minutes INTEGER")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    validate_secure_runtime_config(settings)
    engine = get_engine(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(backfill_sqlite_provider_capability_columns)
        await connection.run_sync(backfill_sqlite_account_auth_columns)
        await connection.run_sync(backfill_sqlite_api_key_public_columns)
        await connection.run_sync(backfill_sqlite_user_provider_columns)
        await connection.run_sync(backfill_sqlite_usage_billing_columns)
        await connection.run_sync(backfill_sqlite_model_pricing_columns)
        await connection.run_sync(backfill_sqlite_hermes_task_billing_columns)
    session_factory = get_session_factory(settings.database_url)
    discovery = ProviderDiscoveryService()
    pricing = OfficialPricingService()
    async with session_factory() as session:
        providers = await session.scalars(
            select(ProviderRecord).where(
                (ProviderRecord.name == "codex") | (ProviderRecord.name == "gemini")
            )
        )
        for provider in providers:
            await discovery.sync_provider_models(session, provider)
            await pricing.sync_provider_pricing(session, provider.name)
            if settings.gemini_acp_prewarm_enabled:
                try:
                    await openai_orchestrator.prewarm_provider(provider)
                except Exception as exc:
                    log_gateway_event(
                        "gateway.gemini_acp.startup_prewarm_failed",
                        request_id="startup-prewarm",
                        provider=provider.name,
                        model=f"{provider.name}:{provider.exposed_model}",
                        reason=str(exc),
                    )
    runner: HermesTaskRunner | None = None
    if settings.hermes_enabled:
        runner = HermesTaskRunner(
            sessionmaker=session_factory,
            max_concurrent_tasks=settings.hermes_max_concurrent_tasks,
            task_max_runtime_seconds=settings.hermes_task_max_runtime_seconds,
        )
        app.state.hermes_task_runner = runner
        await runner.requeue_open_tasks()
        await runner.start()
    try:
        yield
    finally:
        if runner is not None:
            await runner.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="AgentHub OpenAI Gateway", lifespan=lifespan)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(health_router)
    app.include_router(hermes_router)
    app.include_router(internal_public_gateway_router)
    app.include_router(openai_router)
    app.include_router(portal_router)
    app.include_router(user_router, prefix="/user")
    app.include_router(user_router, prefix="/portal")
    return app


app = create_app()
