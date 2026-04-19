from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.orchestration.chat import ChatOrchestrator
from app.registry.service import ProviderRegistry

router = APIRouter(prefix="/v1", tags=["openai"])
registry = ProviderRegistry()
orchestrator = ChatOrchestrator()


@router.get("/models")
async def list_models(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    return {"object": "list", "data": await registry.list_public_models(session)}


@router.post("/chat/completions")
async def create_chat_completion(payload: dict[str, object]) -> dict[str, object]:
    return await orchestrator.run(payload)
