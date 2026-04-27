from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.registry.service import ProviderRegistry


def hermes_model_id(settings: Settings | None = None) -> str | None:
    settings = settings or Settings()
    if not settings.hermes_enabled:
        return None
    return f"hermes:{settings.hermes_model}"


def hermes_model_payload(settings: Settings | None = None) -> dict[str, object] | None:
    model_id = hermes_model_id(settings)
    if model_id is None:
        return None
    return {
        "id": model_id,
        "object": "model",
        "created": 0,
        "owned_by": "hermes",
    }


async def list_platform_models(
    session: AsyncSession,
    registry: ProviderRegistry | None = None,
    settings: Settings | None = None,
) -> list[dict[str, object]]:
    registry = registry or ProviderRegistry()
    models = list(await registry.list_public_models(session))
    hermes_model = hermes_model_payload(settings)
    if hermes_model is not None:
        models.append(hermes_model)
    return sorted(models, key=lambda item: str(item["id"]))
