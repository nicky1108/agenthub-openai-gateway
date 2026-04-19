from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.registry.service import ProviderRegistry

router = APIRouter(prefix="/v1", tags=["openai"])
registry = ProviderRegistry()


@router.get("/models")
async def list_models(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    return {"object": "list", "data": await registry.list_public_models(session)}
