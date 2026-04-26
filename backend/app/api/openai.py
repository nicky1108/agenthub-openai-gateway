import json
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthContext, auth_service, require_api_key
from app.billing.service import UsageSnapshot, billing_service
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
from app.services import builtin_tools
from app.services.provider_presets import resolved_custom_provider_models

router = APIRouter(prefix="/v1", tags=["openai"])
registry = ProviderRegistry()
orchestrator = ChatOrchestrator()
MAX_BUILTIN_TOOL_ROUNDS = 3


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


def combine_usage_snapshots(usages: list[UsageSnapshot]) -> UsageSnapshot:
    if not usages:
        return UsageSnapshot(input_tokens=0, output_tokens=0, cached_input_tokens=0, token_source="estimated")
    token_sources = {usage.token_source for usage in usages}
    token_source = token_sources.pop() if len(token_sources) == 1 else "mixed"
    return UsageSnapshot(
        input_tokens=sum(usage.input_tokens for usage in usages),
        output_tokens=sum(usage.output_tokens for usage in usages),
        cached_input_tokens=sum(usage.cached_input_tokens for usage in usages),
        token_source=token_source,
    )


def apply_direct_web_fetch_fallback(
    result: dict[str, Any],
    tool_messages: list[dict[str, str]],
    original_messages: list[dict[str, Any]],
) -> dict[str, Any]:
    if not tool_messages:
        return result
    should_use_direct_answer = builtin_tools.result_claims_web_fetch_unavailable(
        result
    ) or builtin_tools.result_omits_requested_weather_date(result, original_messages, tool_messages)
    if not should_use_direct_answer:
        return result
    direct_answer = builtin_tools.direct_answer_from_tool_messages(tool_messages)
    if direct_answer is None:
        return result
    return builtin_tools.replace_result_content(result, direct_answer)


async def run_platform_completion_with_builtin_tools(
    request_payload: dict[str, Any],
    session: AsyncSession,
) -> tuple[dict[str, Any], list[UsageSnapshot], list[dict[str, Any]]]:
    if not builtin_tools.request_enables_web_fetch(request_payload):
        return await orchestrator.run(request_payload, session), [], list(request_payload["messages"])

    current_payload = builtin_tools.with_default_web_fetch_tool_choice(
        {**request_payload, "stream": False, "messages": list(request_payload["messages"])}
    )
    tool_round_usages: list[UsageSnapshot] = []
    last_tool_messages: list[dict[str, str]] = []
    for _ in range(MAX_BUILTIN_TOOL_ROUNDS):
        result = await orchestrator.run(current_payload, session)
        assistant_message = builtin_tools.result_assistant_message(result)
        if assistant_message is None:
            return result, tool_round_usages, list(current_payload["messages"])
        tool_messages = await builtin_tools.execute_builtin_tool_calls(assistant_message)
        if not tool_messages:
            if not builtin_tools.tool_choice_forces_web_fetch(current_payload):
                return (
                    apply_direct_web_fetch_fallback(result, last_tool_messages, request_payload["messages"]),
                    tool_round_usages,
                    list(current_payload["messages"]),
                )
            synthetic_message = builtin_tools.synthesize_web_fetch_assistant_message(current_payload)
            if synthetic_message is None:
                return result, tool_round_usages, list(current_payload["messages"])
            tool_messages = await builtin_tools.execute_builtin_tool_calls(synthetic_message)
            if not tool_messages:
                return result, tool_round_usages, list(current_payload["messages"])
        last_tool_messages = tool_messages
        context_message = builtin_tools.tool_messages_to_context_message(tool_messages)
        tool_round_usages.append(billing_service.usage_from_result(current_payload["messages"], result))
        next_payload = {**current_payload}
        if builtin_tools.tool_choice_forces_web_fetch(next_payload):
            next_payload["tool_choice"] = "none"
        current_payload = {
            **next_payload,
            "messages": [*list(current_payload["messages"]), context_message],
        }

    result = await orchestrator.run({**current_payload, "tool_choice": "none"}, session)
    result = apply_direct_web_fetch_fallback(result, last_tool_messages, request_payload["messages"])
    return result, tool_round_usages, list(current_payload["messages"])


async def prepare_stream_payload_with_builtin_tools(
    request_payload: dict[str, Any],
    session: AsyncSession,
) -> tuple[dict[str, Any], list[UsageSnapshot], dict[str, Any] | None]:
    if not builtin_tools.request_enables_web_fetch(request_payload):
        return request_payload, [], None

    probe_payload = builtin_tools.with_default_web_fetch_tool_choice(
        {**request_payload, "stream": False, "messages": list(request_payload["messages"])}
    )
    result = await orchestrator.run(probe_payload, session)
    assistant_message = builtin_tools.result_assistant_message(result)
    if assistant_message is None:
        return request_payload, [], result
    tool_messages = await builtin_tools.execute_builtin_tool_calls(assistant_message)
    if not tool_messages:
        if not builtin_tools.tool_choice_forces_web_fetch(probe_payload):
            return request_payload, [], result
        synthetic_message = builtin_tools.synthesize_web_fetch_assistant_message(probe_payload)
        if synthetic_message is None:
            return request_payload, [], result
        tool_messages = await builtin_tools.execute_builtin_tool_calls(synthetic_message)
        if not tool_messages:
            return request_payload, [], result
    context_message = builtin_tools.tool_messages_to_context_message(tool_messages)

    resolved_messages = [*list(probe_payload["messages"]), context_message]
    resolved_payload = {
        **request_payload,
        "messages": resolved_messages,
        "stream": True,
        "tool_choice": "none",
    }
    usage = billing_service.usage_from_result(probe_payload["messages"], result)
    return resolved_payload, [usage], None


async def stream_chat_completion_result(result: dict[str, Any]):
    choices = result.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices else {}
    message = choice.get("message", {}) if isinstance(choice, dict) else {}
    content = message.get("content", "") if isinstance(message, dict) else ""
    finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
    if content:
        yield (
            "data: "
            + json.dumps(
                {
                    "id": result.get("id", "chatcmpl-result"),
                    "object": "chat.completion.chunk",
                    "model": result.get("model"),
                    "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
                }
            )
            + "\n\n"
        )
    finish_payload: dict[str, Any] = {
        "id": result.get("id", "chatcmpl-result"),
        "object": "chat.completion.chunk",
        "model": result.get("model"),
        "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason or "stop"}],
    }
    usage = result.get("usage")
    if isinstance(usage, dict):
        finish_payload["usage"] = usage
    yield "data: " + json.dumps(finish_payload) + "\n\n"
    yield "data: [DONE]\n\n"


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

            stream_request = request
            stream_provider = provider
            pre_stream_usage: list[UsageSnapshot] = []
            pre_stream_result: dict[str, Any] | None = None
            if builtin_tools.request_enables_web_fetch(request_payload):
                current_phase = "builtin_tools.resolve"
                stream_payload, pre_stream_usage, pre_stream_result = await prepare_stream_payload_with_builtin_tools(
                    {
                        **request_payload,
                        "model": f"{request.provider_name}:{request.provider_model}",
                    },
                    session,
                )
                if pre_stream_result is None:
                    stream_request, stream_provider = await orchestrator.prepare(stream_payload, session)

            async def billable_stream():
                assistant_text = ""
                usage_payload: dict[str, Any] | None = None
                first_chunk_logged = False
                try:
                    stream_source = (
                        stream_chat_completion_result(pre_stream_result)
                        if pre_stream_result is not None
                        else orchestrator.stream_prepared(stream_request, stream_provider)
                    )
                    async for chunk in stream_source:
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
                                                        provider=stream_provider.name,
                                                        model=payload.model,
                                                        elapsed_ms=elapsed_ms(started_at),
                                                    )
                                                    first_chunk_logged = True
                        yield chunk
                except Exception:
                    log_gateway_event(
                        "gateway.request.failed",
                        request_id=request_id,
                        provider=stream_provider.name,
                        model=payload.model,
                        phase="stream.execute",
                        elapsed_ms=elapsed_ms(started_at),
                    )
                    await auth_service.record_usage(session, auth, stream_provider.name, payload.model, "error")
                    raise
                usage = combine_usage_snapshots(
                    [
                        *pre_stream_usage,
                        billing_service.usage_from_stream(stream_request.messages, assistant_text, usage_payload),
                    ]
                )
                current_settle_started = perf_counter()
                await billing_service.settle_inference(
                    session,
                    auth,
                    stream_provider.name,
                    payload.model,
                    quote.pricing,
                    usage,
                )
                log_gateway_event(
                    "gateway.billing.settle",
                    request_id=request_id,
                    provider=stream_provider.name,
                    model=payload.model,
                    elapsed_ms=elapsed_ms(current_settle_started),
                )
                log_gateway_event(
                    "gateway.request.complete",
                    request_id=request_id,
                    provider=stream_provider.name,
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
        result, tool_round_usages, final_request_messages = await run_platform_completion_with_builtin_tools(
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
        usage = combine_usage_snapshots(
            [*tool_round_usages, billing_service.usage_from_result(final_request_messages, result)]
        )
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
        detail = (
            f"model or provider '{payload.model}' not found"
            if ":" not in payload.model
            else f"provider '{exc.provider_name}' not found"
        )
        raise HTTPException(
            status_code=404,
            detail=detail,
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
