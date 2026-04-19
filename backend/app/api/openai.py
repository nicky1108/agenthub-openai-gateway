from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.orchestration.chat import ChatOrchestrator
from app.registry.service import ProviderRegistry

router = APIRouter(prefix="/v1", tags=["openai"])
registry = ProviderRegistry()
orchestrator = ChatOrchestrator()


class ChatCompletionCreate(BaseModel):
    model: str
    messages: list[dict[str, Any]]
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop: str | list[str] | None = None

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        provider_name, separator, provider_model = value.partition(":")
        if not separator or not provider_name or not provider_model:
            raise ValueError("must be in '<provider>:<model>' format")
        return value


@router.get("/models")
async def list_models(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    return {"object": "list", "data": await registry.list_public_models(session)}


@router.post("/chat/completions")
async def create_chat_completion(
    payload: ChatCompletionCreate,
    session: AsyncSession = Depends(get_session),
):
    request_payload = payload.model_dump()
    if request_payload["stream"]:
        return StreamingResponse(
            orchestrator.stream(request_payload, session),
            media_type="text/event-stream",
        )
    return await orchestrator.run(request_payload, session)
