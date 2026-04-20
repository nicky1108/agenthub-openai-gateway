from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import ProviderModelRecord, ProviderRecord


class ProviderNotFoundError(LookupError):
    def __init__(self, provider_name: str) -> None:
        super().__init__(provider_name)
        self.provider_name = provider_name


class ProviderRegistry:
    async def list_public_models(self, session: AsyncSession) -> list[dict[str, object]]:
        provider_rows = await session.scalars(
            select(ProviderRecord)
            .where(or_(ProviderRecord.http_enabled.is_(True), ProviderRecord.cli_enabled.is_(True)))
            .order_by(ProviderRecord.name.asc())
        )
        rows = list(provider_rows)
        provider_ids = [row.id for row in rows]
        model_rows: list[ProviderModelRecord] = []
        if provider_ids:
            result = await session.scalars(
                select(ProviderModelRecord)
                .where(
                    ProviderModelRecord.provider_id.in_(provider_ids),
                    ProviderModelRecord.enabled.is_(True),
                )
                .order_by(ProviderModelRecord.exposed_model_id.asc())
            )
            model_rows = list(result)
        models: list[dict[str, object]] = []
        model_rows_by_provider: dict[int, list[ProviderModelRecord]] = {}
        for row in model_rows:
            model_rows_by_provider.setdefault(row.provider_id, []).append(row)

        for provider in rows:
            provider_models = model_rows_by_provider.get(provider.id, [])
            if provider_models:
                for row in provider_models:
                    models.append(
                        {
                            "id": row.exposed_model_id,
                            "object": "model",
                            "created": 0,
                            "owned_by": provider.name,
                        }
                    )
                continue

            models.append(
                {
                    "id": f"{provider.name}:{provider.exposed_model}",
                    "object": "model",
                    "created": 0,
                    "owned_by": provider.name,
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
