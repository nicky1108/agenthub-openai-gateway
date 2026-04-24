import json
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthContext, auth_service, require_api_key
from app.billing.service import billing_service
from app.core.db import get_session
from app.orchestration.chat import ChatOrchestrator
from app.registry.service import ProviderNotFoundError, ProviderRegistry
from app.runtime.logging import elapsed_ms, log_gateway_event, new_request_id

router = APIRouter(prefix="/v1", tags=["openai"])
registry = ProviderRegistry()
orchestrator = ChatOrchestrator()


class ChatCompletionCreate(BaseModel):
    model_config = ConfigDict(extra="allow")

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
    request_id = new_request_id()
    started_at = perf_counter()
    current_phase = "request.start"
    log_gateway_event(
        "gateway.request.start",
        request_id=request_id,
        provider=provider_name,
        model=payload.model,
        stream=payload.stream,
    )
    try:
        if request_payload["stream"]:
            request_payload["_request_id"] = request_id
            current_phase = "provider.prepare"
            request, provider = await orchestrator.prepare(request_payload, session)
            log_gateway_event(
                "gateway.provider.prepare",
                request_id=request_id,
                provider=provider.name,
                route_policy=provider.route_policy,
                elapsed_ms=elapsed_ms(started_at),
            )
            current_phase = "billing.quote"
            quote = await billing_service.quote_request(
                session,
                auth.account,
                request.provider_name,
                request.provider_model,
                request.messages,
                request.max_tokens,
            )
            log_gateway_event(
                "gateway.billing.quote",
                request_id=request_id,
                provider=provider.name,
                model=payload.model,
                estimated_credits=quote.estimated_credits_ceiling,
                elapsed_ms=elapsed_ms(started_at),
            )

            async def billable_stream():
                assistant_text = ""
                usage_payload: dict[str, Any] | None = None
                first_chunk_logged = False
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
                                                if delta.get("content") and not first_chunk_logged:
                                                    log_gateway_event(
                                                        "gateway.stream.first_chunk",
                                                        request_id=request_id,
                                                        provider=provider.name,
                                                        model=payload.model,
                                                        elapsed_ms=elapsed_ms(started_at),
                                                    )
                                                    first_chunk_logged = True
                        yield chunk
                except Exception:
                    log_gateway_event(
                        "gateway.request.failed",
                        request_id=request_id,
                        provider=provider.name,
                        model=payload.model,
                        phase="stream.execute",
                        elapsed_ms=elapsed_ms(started_at),
                    )
                    await auth_service.record_usage(session, auth, provider.name, payload.model, "error")
                    raise
                usage = billing_service.usage_from_stream(request.messages, assistant_text, usage_payload)
                current_settle_started = perf_counter()
                await billing_service.settle_inference(
                    session,
                    auth,
                    provider.name,
                    payload.model,
                    quote.pricing,
                    usage,
                )
                log_gateway_event(
                    "gateway.billing.settle",
                    request_id=request_id,
                    provider=provider.name,
                    model=payload.model,
                    elapsed_ms=elapsed_ms(current_settle_started),
                )
                log_gateway_event(
                    "gateway.request.complete",
                    request_id=request_id,
                    provider=provider.name,
                    model=payload.model,
                    stream=True,
                    elapsed_ms=elapsed_ms(started_at),
                )

            return StreamingResponse(
                billable_stream(),
                media_type="text/event-stream",
            )
        current_phase = "provider.prepare"
        request_payload["_request_id"] = request_id
        request, provider = await orchestrator.prepare(request_payload, session)
        log_gateway_event(
            "gateway.provider.prepare",
            request_id=request_id,
            provider=provider.name,
            route_policy=provider.route_policy,
            elapsed_ms=elapsed_ms(started_at),
        )
        current_phase = "billing.quote"
        quote = await billing_service.quote_request(
            session,
            auth.account,
            request.provider_name,
            request.provider_model,
            request.messages,
            request.max_tokens,
        )
        log_gateway_event(
            "gateway.billing.quote",
            request_id=request_id,
            provider=provider.name,
            model=payload.model,
            estimated_credits=quote.estimated_credits_ceiling,
            elapsed_ms=elapsed_ms(started_at),
        )
        current_phase = "provider.execute"
        result = await orchestrator.run(
            {
                **request_payload,
                "model": f"{request.provider_name}:{request.provider_model}",
            },
            session,
        )
        log_gateway_event(
            "gateway.provider.complete",
            request_id=request_id,
            provider=provider.name,
            model=payload.model,
            elapsed_ms=elapsed_ms(started_at),
        )
        usage = billing_service.usage_from_result(payload.messages, result)
        current_phase = "billing.settle"
        settle_started = perf_counter()
        await billing_service.settle_inference(
            session,
            auth,
            provider.name,
            payload.model,
            quote.pricing,
            usage,
        )
        log_gateway_event(
            "gateway.billing.settle",
            request_id=request_id,
            provider=provider.name,
            model=payload.model,
            elapsed_ms=elapsed_ms(settle_started),
        )
        log_gateway_event(
            "gateway.request.complete",
            request_id=request_id,
            provider=provider.name,
            model=payload.model,
            stream=False,
            elapsed_ms=elapsed_ms(started_at),
        )
        return result
    except ProviderNotFoundError as exc:
        log_gateway_event(
            "gateway.request.failed",
            request_id=request_id,
            provider=exc.provider_name,
            model=payload.model,
            phase=current_phase,
            elapsed_ms=elapsed_ms(started_at),
        )
        await auth_service.record_usage(session, auth, exc.provider_name, payload.model, "error")
        raise HTTPException(
            status_code=404,
            detail=f"provider '{exc.provider_name}' not found",
        ) from exc
    except HTTPException:
        log_gateway_event(
            "gateway.request.failed",
            request_id=request_id,
            provider=provider_name,
            model=payload.model,
            phase=current_phase,
            elapsed_ms=elapsed_ms(started_at),
        )
        raise
    except Exception:
        log_gateway_event(
            "gateway.request.failed",
            request_id=request_id,
            provider=provider_name,
            model=payload.model,
            phase=current_phase,
            elapsed_ms=elapsed_ms(started_at),
        )
        raise
