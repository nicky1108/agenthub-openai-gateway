from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.engine import Connection

from app.api.admin import router as admin_router
from app.api.health import router as health_router
from app.api.openai import router as openai_router
from app.core.db import get_engine
from app.core.models import Base
from app.core.settings import Settings


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    engine = get_engine(Settings().database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(backfill_sqlite_provider_capability_columns)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="AgentHub OpenAI Gateway", lifespan=lifespan)
    app.include_router(admin_router)
    app.include_router(health_router)
    app.include_router(openai_router)
    return app


app = create_app()
