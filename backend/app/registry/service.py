from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import ProviderRecord


class ProviderRegistry:
    async def list_public_models(self, session: AsyncSession) -> list[dict[str, object]]:
        rows = await session.scalars(select(ProviderRecord).order_by(ProviderRecord.name.asc()))
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
