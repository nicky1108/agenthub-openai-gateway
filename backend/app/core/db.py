from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.settings import Settings


@lru_cache
def get_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, future=True)


@lru_cache
def get_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(database_url), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    session_factory = get_session_factory(Settings().database_url)
    async with session_factory() as session:
        yield session
