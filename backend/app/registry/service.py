from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import ProviderRecord


class ProviderNotFoundError(LookupError):
    def __init__(self, provider_name: str) -> None:
        super().__init__(provider_name)
        self.provider_name = provider_name


class ProviderRegistry:
    async def list_public_models(self, session: AsyncSession) -> list[dict[str, object]]:
        rows = await session.scalars(
            select(ProviderRecord)
            .where(or_(ProviderRecord.http_enabled.is_(True), ProviderRecord.cli_enabled.is_(True)))
            .order_by(ProviderRecord.name.asc())
        )
        models: list[dict[str, object]] = []
        for row in rows:
            models.append(
                {
                    "id": f"{row.name}:default",
                    "object": "model",
                    "created": 0,
                    "owned_by": row.name,
                }
            )
        return models

    async def get_provider(self, session: AsyncSession, provider_name: str) -> ProviderRecord:
        row = await session.scalar(
            select(ProviderRecord).where(ProviderRecord.name == provider_name)
        )
        if row is None:
            raise ProviderNotFoundError(provider_name)
        return row
