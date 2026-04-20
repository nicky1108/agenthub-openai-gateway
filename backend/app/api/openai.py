import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthContext, auth_service, require_api_key
from app.billing.service import billing_service
from app.core.db import get_session
from app.orchestration.chat import ChatOrchestrator
from app.registry.service import ProviderNotFoundError, ProviderRegistry

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
async def list_models(
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_key),
) -> dict[str, object]:
    payload = {"object": "list", "data": await registry.list_public_models(session)}
    await auth_service.record_usage(session, auth, None, None, "success")
    return payload


@router.post("/chat/completions")
async def create_chat_completion(
    payload: ChatCompletionCreate,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_key),
):
    request_payload = payload.model_dump()
    provider_name = payload.model.split(":", 1)[0]
    try:
        if request_payload["stream"]:
            request, provider = await orchestrator.prepare(request_payload, session)
            quote = await billing_service.quote_request(
                session,
                auth.account,
                request.provider_name,
                request.provider_model,
                request.messages,
                request.max_tokens,
            )

            async def billable_stream():
                assistant_text = ""
                usage_payload: dict[str, Any] | None = None
                try:
                    async for chunk in orchestrator.stream_prepared(request, provider):
                        if chunk.startswith("data: "):
                            data = chunk.removeprefix("data: ").strip()
                            if data and data != "[DONE]":
                                try:
                                    payload_chunk = json.loads(data)
                                except json.JSONDecodeError:
                                    payload_chunk = None
                                if isinstance(payload_chunk, dict):
                                    usage = payload_chunk.get("usage")
                                    if isinstance(usage, dict):
                                        usage_payload = usage
                                    choices = payload_chunk.get("choices")
                                    if isinstance(choices, list):
                                        for choice in choices:
                                            delta = choice.get("delta", {})
                                            if isinstance(delta, dict):
                                                assistant_text += str(delta.get("content", ""))
                        yield chunk
                except Exception:
                    await auth_service.record_usage(session, auth, provider.name, payload.model, "error")
                    raise
                usage = billing_service.usage_from_stream(request.messages, assistant_text, usage_payload)
                await billing_service.settle_inference(
                    session,
                    auth,
                    provider.name,
                    payload.model,
                    quote.pricing,
                    usage,
                )

            return StreamingResponse(
                billable_stream(),
                media_type="text/event-stream",
            )
        request, provider = await orchestrator.prepare(request_payload, session)
        quote = await billing_service.quote_request(
            session,
            auth.account,
            request.provider_name,
            request.provider_model,
            request.messages,
            request.max_tokens,
        )
        result = await orchestrator.run(
            {
                **request_payload,
                "model": f"{request.provider_name}:{request.provider_model}",
            },
            session,
        )
        usage = billing_service.usage_from_result(payload.messages, result)
        await billing_service.settle_inference(
            session,
            auth,
            provider.name,
            payload.model,
            quote.pricing,
            usage,
        )
        return result
    except ProviderNotFoundError as exc:
        await auth_service.record_usage(session, auth, exc.provider_name, payload.model, "error")
        raise HTTPException(
            status_code=404,
            detail=f"provider '{exc.provider_name}' not found",
        ) from exc
