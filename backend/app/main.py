from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.admin import router as admin_router
from app.api.health import router as health_router
from app.core.db import engine
from app.core.models import Base


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="AgentHub OpenAI Gateway", lifespan=lifespan)
    app.include_router(admin_router)
    app.include_router(health_router)
    return app


app = create_app()
