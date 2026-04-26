from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.portal import require_portal_account, usage_records as portal_usage_records
from app.adapters.base import ChatRequest
from app.adapters.http.anthropic_messages import AnthropicMessagesAdapter
from app.auth.service import generate_api_key, hash_api_key
from app.core.db import get_session
from app.core.models import AccountRecord, ApiKeyRecord, UsageRecord, UserProviderRecord
from app.core.settings import Settings
from app.services.provider_guardrails import (
    ensure_safe_provider_protocol,
    ensure_safe_provider_slug,
    ensure_safe_provider_url,
)

router = APIRouter(tags=["user"])


class ApiKeyUpdatePayload(BaseModel):
    name: str | None = None
    per_minute: int | None = None
    per_hour: int | None = None
    per_day: int | None = None


class ProviderUpdatePayload(BaseModel):
    name: str | None = None
    protocol: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    description: str | None = None


class ProviderProbePayload(BaseModel):
    protocol: str = "openai"
    base_url: str
    api_key: str
    candidate_models: list[str] = []


def _empty_probe_result() -> dict[str, Any]:
    return {
        "models_endpoint_supported": False,
        "detected_models": [],
        "completion_probe_ok": False,
        "completion_probe_model": None,
        "detail": None,
    }


def _normalized_detected_models(protocol: str, models: list[str]) -> list[str]:
    if protocol == "anthropic":
        return [model for model in models if model.startswith("claude")]
    return models


async def run_provider_probe(
    *,
    protocol: str,
    base_url: str,
    api_key: str,
    candidate_models: list[str],
) -> dict[str, Any]:
    result = _empty_probe_result()
    normalized_protocol = ensure_safe_provider_protocol(protocol)

    if normalized_protocol == "anthropic":
        adapter = AnthropicMessagesAdapter(base_url=base_url, api_key=api_key, headers={})
        try:
            detected_models = _normalized_detected_models(normalized_protocol, await adapter.list_models())
            result["models_endpoint_supported"] = True
            result["detected_models"] = detected_models
        except Exception:
            pass

        probe_candidates = list(result["detected_models"]) or candidate_models
        for model_id in probe_candidates:
            try:
                completion_payload = await adapter.chat(
                    ChatRequest(
                        provider_name="custom-provider",
                        provider_model=model_id,
                        messages=[{"role": "user", "content": "Reply with only OK"}],
                        stream=False,
                        max_tokens=16,
                    )
                )
                if isinstance(completion_payload, dict) and isinstance(completion_payload.get("choices"), list):
                    result["completion_probe_ok"] = True
                    result["completion_probe_model"] = model_id
                    result["detail"] = None
                    return result
            except httpx.HTTPStatusError as exc:
                result["detail"] = f"probe failed with status {exc.response.status_code}"
            except Exception as exc:
                result["detail"] = str(exc)
    else:
        async with httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=25.0,
            follow_redirects=True,
        ) as client:
            try:
                models_response = await client.get("/models")
                if models_response.status_code == 200:
                    models_payload = models_response.json()
                    if isinstance(models_payload, dict) and isinstance(models_payload.get("data"), list):
                        result["models_endpoint_supported"] = True
                        result["detected_models"] = [
                            item["id"]
                            for item in models_payload["data"]
                            if isinstance(item, dict) and isinstance(item.get("id"), str)
                        ]
            except Exception:
                pass

            probe_candidates = list(result["detected_models"]) or candidate_models
            for model_id in probe_candidates:
                try:
                    response = await client.post(
                        "/chat/completions",
                        json={
                            "model": model_id,
                            "messages": [{"role": "user", "content": "Reply with only OK"}],
                            "stream": False,
                            "max_tokens": 16,
                        },
                    )
                    if response.status_code != 200:
                        result["detail"] = f"probe failed with status {response.status_code}"
                        continue
                    completion_payload = response.json()
                    if isinstance(completion_payload, dict) and isinstance(completion_payload.get("choices"), list):
                        result["completion_probe_ok"] = True
                        result["completion_probe_model"] = model_id
                        result["detail"] = None
                        return result
                except Exception as exc:
                    result["detail"] = str(exc)

    if not probe_candidates:
        result["detail"] = "provider does not expose /models and no candidate model list was supplied"
    return result


def apply_probe_result(provider: UserProviderRecord, result: dict[str, Any]) -> None:
    provider.last_probe_at = datetime.now(timezone.utc)
    provider.last_probe_ok = bool(result.get("completion_probe_ok"))
    provider.last_probe_model = (
        str(result["completion_probe_model"])
        if isinstance(result.get("completion_probe_model"), str)
        else None
    )
    provider.last_probe_detail = str(result["detail"]) if isinstance(result.get("detail"), str) else None
    detected_models = result.get("detected_models")
    if not isinstance(detected_models, list):
        detected_models = []
    provider.last_detected_models_json = json.dumps([item for item in detected_models if isinstance(item, str)])


def _deserialize_detected_models(payload: str | None) -> list[str]:
    if not payload:
        return []
    try:
        decoded = json.loads(payload)
    except (TypeError, ValueError):
        return []
    if not isinstance(decoded, list):
        return []
    return [item for item in decoded if isinstance(item, str)]


def serialize_user_provider(provider: UserProviderRecord) -> dict[str, Any]:
    protocol = provider.protocol if isinstance(provider.protocol, str) and provider.protocol else "openai"
    return {
        "id": provider.id,
        "account_id": provider.account_id,
        "slug": provider.slug,
        "name": provider.name,
        "protocol": protocol,
        "base_url": provider.base_url,
        "description": provider.description,
        "status": provider.status,
        "last_probe_at": provider.last_probe_at.isoformat() if provider.last_probe_at else None,
        "last_probe_ok": provider.last_probe_ok,
        "last_probe_model": provider.last_probe_model,
        "last_probe_detail": provider.last_probe_detail,
        "last_detected_models": _deserialize_detected_models(provider.last_detected_models_json),
    }


def _validate_limit(value: int | None, label: str) -> int | None:
    if value is None:
        return None
    if value <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{label} must be a positive integer")
    return value


async def _usage_counts_by_key(session: AsyncSession, key_ids: list[int]) -> dict[int, dict[str, int]]:
    if not key_ids:
        return {}
    rows = list(
        await session.execute(
            select(
                UsageRecord.api_key_id,
                func.count(UsageRecord.id),
                func.sum(case((UsageRecord.outcome == "limited", 1), else_=0)),
            )
            .where(UsageRecord.api_key_id.in_(key_ids))
            .group_by(UsageRecord.api_key_id)
        )
    )
    return {
        int(row[0]): {
            "total_requests": int(row[1] or 0),
            "limited_requests": int(row[2] or 0),
        }
        for row in rows
        if row[0] is not None
    }


def _serialize_api_key(key: ApiKeyRecord, usage_counts: dict[str, int] | None = None) -> dict[str, Any]:
    usage_counts = usage_counts or {"total_requests": 0, "limited_requests": 0}
    return {
        "id": key.id,
        "account_id": key.account_id,
        "name": key.name,
        "key_prefix": key.key_prefix,
        "status": key.status,
        "created_at": key.created_at.isoformat(),
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
        "per_minute": key.per_minute,
        "per_hour": key.per_hour,
        "per_day": key.per_day,
        "total_requests": usage_counts["total_requests"],
        "limited_requests": usage_counts["limited_requests"],
    }


@router.get("/api-keys")
async def list_api_keys(
    session: AsyncSession = Depends(get_session),
    account: AccountRecord = Depends(require_portal_account),
) -> list[dict[str, Any]]:
    keys = list(
        await session.scalars(
            select(ApiKeyRecord)
            .where(
                ApiKeyRecord.account_id == account.id,
                ApiKeyRecord.status == "active",
            )
            .order_by(ApiKeyRecord.id.asc())
        )
    )
    usage_counts = await _usage_counts_by_key(session, [key.id for key in keys])
    return [_serialize_api_key(key, usage_counts.get(key.id)) for key in keys]


@router.get("/usage/records")
async def list_usage_records(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    api_key_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    account: AccountRecord = Depends(require_portal_account),
) -> dict[str, Any]:
    return await portal_usage_records(
        limit=limit,
        offset=offset,
        api_key_id=api_key_id,
        account=account,
        session=session,
    )


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def create_user_api_key(
    name: str,
    per_minute: int | None = None,
    per_hour: int | None = None,
    per_day: int | None = None,
    session: AsyncSession = Depends(get_session),
    account: AccountRecord = Depends(require_portal_account),
) -> dict[str, Any]:
    key_name = name.strip()
    if not key_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")

    prefix, token = generate_api_key()
    key_record = ApiKeyRecord(
        account_id=account.id,
        name=key_name,
        key_prefix=prefix,
        secret_hash=hash_api_key(token),
        per_minute=_validate_limit(per_minute, "per_minute"),
        per_hour=_validate_limit(per_hour, "per_hour"),
        per_day=_validate_limit(per_day, "per_day"),
    )
    session.add(key_record)
    await session.commit()
    await session.refresh(key_record)
    return {"api_key": token, **_serialize_api_key(key_record)}


@router.patch("/api-keys/{key_id}")
async def update_api_key(
    key_id: int,
    payload: ApiKeyUpdatePayload,
    session: AsyncSession = Depends(get_session),
    account: AccountRecord = Depends(require_portal_account),
) -> dict[str, Any]:
    key = await session.scalar(
        select(ApiKeyRecord).where(
            ApiKeyRecord.id == key_id,
            ApiKeyRecord.account_id == account.id,
            ApiKeyRecord.status == "active",
        )
    )
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    fields_set = payload.model_fields_set
    if "name" in fields_set and payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
        key.name = name
    if "per_minute" in fields_set:
        key.per_minute = _validate_limit(payload.per_minute, "per_minute")
    if "per_hour" in fields_set:
        key.per_hour = _validate_limit(payload.per_hour, "per_hour")
    if "per_day" in fields_set:
        key.per_day = _validate_limit(payload.per_day, "per_day")

    await session.commit()
    await session.refresh(key)
    usage_counts = await _usage_counts_by_key(session, [key.id])
    return _serialize_api_key(key, usage_counts.get(key.id))


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: int,
    session: AsyncSession = Depends(get_session),
    account: AccountRecord = Depends(require_portal_account),
) -> dict[str, str]:
    key = await session.scalar(
        select(ApiKeyRecord).where(ApiKeyRecord.id == key_id, ApiKeyRecord.account_id == account.id)
    )
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    key.status = "revoked"
    key.revoked_at = datetime.now(timezone.utc)
    await session.commit()
    return {"status": "revoked"}


@router.post("/api-keys/{key_id}/revoke")
async def revoke_api_key(
    key_id: int,
    session: AsyncSession = Depends(get_session),
    account: AccountRecord = Depends(require_portal_account),
) -> dict[str, str]:
    return await delete_api_key(key_id, session, account)


@router.get("/providers")
async def list_user_providers(
    session: AsyncSession = Depends(get_session),
    account: AccountRecord = Depends(require_portal_account),
) -> list[dict[str, Any]]:
    providers = list(
        await session.scalars(
            select(UserProviderRecord)
            .where(
                UserProviderRecord.account_id == str(account.id),
                UserProviderRecord.status == "active",
            )
            .order_by(UserProviderRecord.slug.asc())
        )
    )
    return [serialize_user_provider(provider) for provider in providers]


@router.post("/providers", status_code=status.HTTP_201_CREATED)
async def add_user_provider(
    name: str,
    base_url: str,
    api_key: str,
    protocol: str = "openai",
    description: str | None = None,
    session: AsyncSession = Depends(get_session),
    account: AccountRecord = Depends(require_portal_account),
) -> dict[str, Any]:
    try:
        safe_slug = ensure_safe_provider_slug(name, Settings().reserved_provider_slugs)
        safe_protocol = ensure_safe_provider_protocol(protocol)
        safe_base_url = ensure_safe_provider_url(base_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    existing = await session.scalar(
        select(UserProviderRecord).where(
            UserProviderRecord.account_id == str(account.id),
            UserProviderRecord.slug == safe_slug,
            UserProviderRecord.status == "active",
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="provider already exists")

    provider = UserProviderRecord(
        account_id=str(account.id),
        slug=safe_slug,
        name=name,
        protocol=safe_protocol,
        base_url=safe_base_url,
        secret_ref=api_key,
        description=description,
    )
    session.add(provider)
    await session.commit()
    await session.refresh(provider)
    return serialize_user_provider(provider)


@router.patch("/providers/{provider_id}")
async def update_user_provider(
    provider_id: int,
    payload: ProviderUpdatePayload,
    session: AsyncSession = Depends(get_session),
    account: AccountRecord = Depends(require_portal_account),
) -> dict[str, Any]:
    provider = await session.scalar(
        select(UserProviderRecord).where(
            UserProviderRecord.id == provider_id,
            UserProviderRecord.account_id == str(account.id),
            UserProviderRecord.status == "active",
        )
    )
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    probe_invalidated = False
    fields_set = payload.model_fields_set
    if "name" in fields_set and payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="provider name is required")
        provider.name = name
    if "protocol" in fields_set and payload.protocol is not None:
        try:
            protocol = ensure_safe_provider_protocol(payload.protocol)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if protocol != provider.protocol:
            provider.protocol = protocol
            probe_invalidated = True
    if "base_url" in fields_set and payload.base_url is not None:
        try:
            base_url = ensure_safe_provider_url(payload.base_url)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if base_url != provider.base_url:
            provider.base_url = base_url
            probe_invalidated = True
    if "api_key" in fields_set and payload.api_key is not None and payload.api_key.strip():
        provider.secret_ref = payload.api_key
        probe_invalidated = True
    if "description" in fields_set:
        provider.description = payload.description

    if probe_invalidated:
        provider.last_probe_at = None
        provider.last_probe_ok = None
        provider.last_probe_model = None
        provider.last_probe_detail = None
        provider.last_detected_models_json = "[]"

    await session.commit()
    await session.refresh(provider)
    return serialize_user_provider(provider)


@router.delete("/providers/{provider_id}")
async def delete_user_provider(
    provider_id: int,
    session: AsyncSession = Depends(get_session),
    account: AccountRecord = Depends(require_portal_account),
) -> dict[str, str]:
    provider = await session.scalar(
        select(UserProviderRecord).where(
            UserProviderRecord.id == provider_id,
            UserProviderRecord.account_id == str(account.id),
        )
    )
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    provider.status = "deleted"
    await session.commit()
    return {"status": "deleted"}


@router.post("/providers/probe")
async def probe_user_provider(
    payload: ProviderProbePayload,
    _: AccountRecord = Depends(require_portal_account),
) -> dict[str, Any]:
    try:
        base_url = ensure_safe_provider_url(payload.base_url)
        protocol = ensure_safe_provider_protocol(payload.protocol)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return await run_provider_probe(
        protocol=protocol,
        base_url=base_url,
        api_key=payload.api_key,
        candidate_models=payload.candidate_models,
    )


@router.post("/providers/{provider_id}/probe")
async def probe_existing_user_provider(
    provider_id: int,
    session: AsyncSession = Depends(get_session),
    account: AccountRecord = Depends(require_portal_account),
) -> dict[str, Any]:
    provider = await session.scalar(
        select(UserProviderRecord).where(
            UserProviderRecord.id == provider_id,
            UserProviderRecord.account_id == str(account.id),
            UserProviderRecord.status == "active",
        )
    )
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    from app.services.provider_presets import recommended_upstream_models

    result = await run_provider_probe(
        protocol=provider.protocol,
        base_url=provider.base_url,
        api_key=provider.secret_ref,
        candidate_models=recommended_upstream_models(provider.slug, provider.base_url, provider.protocol),
    )
    apply_probe_result(provider, result)
    await session.commit()
    await session.refresh(provider)
    return serialize_user_provider(provider)
