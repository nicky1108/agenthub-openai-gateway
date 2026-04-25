import json
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthContext, auth_service, require_api_key
from app.billing.service import billing_service
from app.core.db import get_session
from app.core.models import UserProviderRecord
from app.orchestration.chat import ChatOrchestrator
from app.registry.service import ProviderNotFoundError, ProviderRegistry
from app.runtime.logging import elapsed_ms, log_gateway_event, new_request_id
from app.services.custom_provider_runtime import (
    CustomProviderRequestError,
    CustomProviderResponseError,
    execute_custom_completion,
    stream_custom_completion,
)
from app.services.provider_presets import resolved_custom_provider_models

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
        if not value or value.startswith(":") or value.endswith(":"):
            raise ValueError("must be a model id or '<provider>:<model>'")
        return value


async def list_user_custom_models(session: AsyncSession, account_id: int) -> list[dict[str, object]]:
    rows = list(
        await session.scalars(
            select(UserProviderRecord)
            .where(
                UserProviderRecord.account_id == str(account_id),
                UserProviderRecord.status == "active",
            )
            .order_by(UserProviderRecord.slug.asc())
        )
    )
    return [
        {
            "id": f"{provider.slug}:{model_name}",
            "object": "model",
            "created": 0,
            "owned_by": provider.slug,
            "source": "custom",
        }
        for provider in rows
        for model_name in resolved_custom_provider_models(
            provider_slug=provider.slug,
            base_url=provider.base_url,
            protocol=provider.protocol,
            detected_models_json=provider.last_detected_models_json,
            preferred_model=provider.last_probe_model,
        )
    ]


async def resolve_user_provider(
    session: AsyncSession,
    account_id: int,
    model_id: str,
) -> tuple[UserProviderRecord, str] | None:
    provider_slug = model_id.split(":", 1)[0] if ":" in model_id else model_id
    provider = await session.scalar(
        select(UserProviderRecord).where(
            UserProviderRecord.account_id == str(account_id),
            UserProviderRecord.slug == provider_slug,
            UserProviderRecord.status == "active",
        )
    )
    if provider is None:
        return None
    provider_model = model_id.split(":", 1)[1] if ":" in model_id else "default"
    return provider, f"{provider.slug}:{provider_model}"


def custom_provider_descriptor(provider: UserProviderRecord) -> dict[str, object]:
    return {
        "base_url": provider.base_url,
        "secret_value": provider.secret_ref,
        "slug": provider.slug,
        "protocol": provider.protocol,
    }


async def route_custom_completion(
    request_payload: dict[str, Any],
    provider: UserProviderRecord,
) -> dict[str, Any]:
    return await execute_custom_completion(request_payload, custom_provider_descriptor(provider))


async def route_custom_completion_stream(
    request_payload: dict[str, Any],
    provider: UserProviderRecord,
):
    async for chunk in stream_custom_completion(request_payload, custom_provider_descriptor(provider)):
        yield chunk


def custom_provider_http_exception(exc: CustomProviderRequestError | CustomProviderResponseError) -> HTTPException:
    if isinstance(exc, CustomProviderRequestError):
        if exc.status_code is not None:
            detail = f"custom provider returned {exc.status_code}"
            if exc.detail:
                detail = f"{detail}: {exc.detail}"
            return HTTPException(status_code=502, detail=detail)
        return HTTPException(status_code=503, detail="custom provider request failed")
    return HTTPException(status_code=502, detail="custom provider returned invalid response")


@router.get("/models")
async def list_models(
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_key),
) -> dict[str, object]:
    platform_models = await registry.list_public_models(session)
    custom_models = await list_user_custom_models(session, auth.account.id)
    payload = {"object": "list", "data": [*platform_models, *custom_models]}
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
        custom_resolution = await resolve_user_provider(session, auth.account.id, payload.model)
        if custom_resolution is not None:
            custom_provider, canonical_model = custom_resolution
            custom_request_payload = {**request_payload, "model": canonical_model}
            if request_payload["stream"]:

                async def custom_stream_response():
                    try:
                        async for chunk in route_custom_completion_stream(custom_request_payload, custom_provider):
                            yield chunk
                    except (CustomProviderRequestError, CustomProviderResponseError):
                        await auth_service.record_usage(session, auth, custom_provider.slug, canonical_model, "error")
                        raise
                    await auth_service.record_usage(session, auth, custom_provider.slug, canonical_model, "success")

                return StreamingResponse(custom_stream_response(), media_type="text/event-stream")

            try:
                result = await route_custom_completion(custom_request_payload, custom_provider)
            except (CustomProviderRequestError, CustomProviderResponseError) as exc:
                await auth_service.record_usage(session, auth, custom_provider.slug, canonical_model, "error")
                raise custom_provider_http_exception(exc) from exc
            await auth_service.record_usage(session, auth, custom_provider.slug, canonical_model, "success")
            return result

        if ":" not in payload.model:
            await auth_service.record_usage(session, auth, payload.model, payload.model, "error")
            raise HTTPException(
                status_code=404,
                detail=f"model or provider '{payload.model}' not found",
            )

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
