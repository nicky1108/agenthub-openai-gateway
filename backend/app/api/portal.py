from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import SESSION_COOKIE_NAME, normalize_timestamp
from app.auth.service import hash_api_key
from app.core.db import get_session
from app.core.models import (
    AccountRecord,
    ApiKeyRecord,
    AuthSessionRecord,
    CreditLedgerRecord,
    UsageRecord,
    UserProviderRecord,
)
from app.registry.service import ProviderRegistry
from app.services.provider_presets import list_provider_presets, resolved_custom_provider_models

router = APIRouter(prefix="/portal", tags=["portal"])
registry = ProviderRegistry()


async def require_portal_account(
    agh_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    session: AsyncSession = Depends(get_session),
) -> AccountRecord:
    if not agh_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing session cookie")

    session_record = await session.scalar(
        select(AuthSessionRecord).where(AuthSessionRecord.session_token_hash == hash_api_key(agh_session))
    )
    if session_record is None or session_record.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session")
    if normalize_timestamp(session_record.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired")

    account = await session.scalar(select(AccountRecord).where(AccountRecord.id == session_record.account_id))
    if account is None or account.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="account is not active")
    return account


@router.get("/dashboard")
async def dashboard(
    account: AccountRecord = Depends(require_portal_account),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    window_24h = now - timedelta(hours=24)
    window_7d = now - timedelta(days=7)

    request_count_24h = (
        await session.scalar(
            select(func.count(UsageRecord.id)).where(
                UsageRecord.account_id == account.id,
                UsageRecord.created_at >= window_24h,
            )
        )
    ) or 0
    request_count_7d = (
        await session.scalar(
            select(func.count(UsageRecord.id)).where(
                UsageRecord.account_id == account.id,
                UsageRecord.created_at >= window_7d,
            )
        )
    ) or 0
    api_key_count = (
        await session.scalar(
            select(func.count(ApiKeyRecord.id)).where(
                ApiKeyRecord.account_id == account.id,
                ApiKeyRecord.status == "active",
            )
        )
    ) or 0
    local_provider_count = (
        await session.scalar(
            select(func.count(UserProviderRecord.id)).where(
                UserProviderRecord.account_id == str(account.id),
                UserProviderRecord.status == "active",
            )
        )
    ) or 0
    custom_provider_slugs = set(
        await session.scalars(
            select(UserProviderRecord.slug).where(
                UserProviderRecord.account_id == str(account.id),
                UserProviderRecord.status == "active",
            )
        )
    )
    recent_usage = list(
        await session.scalars(
            select(UsageRecord)
            .where(UsageRecord.account_id == account.id)
            .order_by(UsageRecord.created_at.desc(), UsageRecord.id.desc())
            .limit(20)
        )
    )
    usage_24h_rows = list(
        await session.scalars(
            select(UsageRecord).where(
                UsageRecord.account_id == account.id,
                UsageRecord.created_at >= window_24h,
            )
        )
    )
    credit_ledger = list(
        await session.scalars(
            select(CreditLedgerRecord)
            .where(CreditLedgerRecord.account_id == account.id)
            .order_by(CreditLedgerRecord.created_at.desc(), CreditLedgerRecord.id.desc())
            .limit(20)
        )
    )

    return {
        "credits_balance": account.credit_balance,
        "api_key_count": api_key_count,
        "request_count_24h": request_count_24h,
        "request_count_7d": request_count_7d,
        "platform_requests_24h": sum(1 for row in usage_24h_rows if row.provider_name not in custom_provider_slugs),
        "custom_requests_24h": sum(1 for row in usage_24h_rows if row.provider_name in custom_provider_slugs),
        "local_provider_count": local_provider_count,
        "account_sync": {
            "linked": True,
            "local_account_id": str(account.id),
            "upstream_account_id": None,
            "upstream_workspace_id": None,
            "local_mirror": {"status": "unified"},
            "sync_queue": {"pending": 0, "failed": 0},
        },
        "recent_usage": [
            {
                "id": row.id,
                "api_key_id": row.api_key_id,
                "provider_name": row.provider_name,
                "model_id": row.model_id,
                "outcome": row.outcome,
                "input_tokens": row.input_tokens,
                "output_tokens": row.output_tokens,
                "cached_input_tokens": row.cached_input_tokens,
                "usd_amount": row.usd_amount,
                "credits_charged": row.credits_charged,
                "created_at": row.created_at.isoformat(),
            }
            for row in recent_usage
        ],
        "credit_ledger": [
            {
                "id": row.id,
                "api_key_id": row.api_key_id,
                "usage_record_id": row.usage_record_id,
                "entry_type": row.entry_type,
                "credits_delta": row.credits_delta,
                "balance_after": row.balance_after,
                "usd_amount": row.usd_amount,
                "provider_name": row.provider_name,
                "model_id": row.model_id,
                "created_at": row.created_at.isoformat(),
            }
            for row in credit_ledger
        ],
    }


@router.get("/catalog")
async def catalog(
    account: AccountRecord = Depends(require_portal_account),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    platform_models = await registry.list_public_models(session)
    custom_provider_rows = list(
        await session.scalars(
            select(UserProviderRecord)
            .where(
                UserProviderRecord.account_id == str(account.id),
                UserProviderRecord.status == "active",
            )
            .order_by(UserProviderRecord.slug.asc())
        )
    )
    return {
        "platform_providers": _group_platform_providers(platform_models),
        "platform_models": [
            {
                "id": str(model["id"]),
                "provider": str(model.get("owned_by") or "platform"),
                "source": "platform",
                "enabled": True,
            }
            for model in platform_models
        ],
        "custom_models": [
            {
                "id": f"{provider.slug}:{model_name}",
                "provider": provider.slug,
                "source": "custom",
                "enabled": provider.status == "active",
            }
            for provider in custom_provider_rows
            for model_name in resolved_custom_provider_models(
                provider_slug=provider.slug,
                base_url=provider.base_url,
                protocol=provider.protocol,
                detected_models_json=provider.last_detected_models_json,
                preferred_model=provider.last_probe_model,
            )
        ],
    }


@router.get("/provider-presets")
async def provider_presets(_: AccountRecord = Depends(require_portal_account)) -> list[dict[str, object]]:
    return list_provider_presets()


@router.post("/sync/retry")
async def retry_sync(_: AccountRecord = Depends(require_portal_account)) -> dict[str, Any]:
    return {"status": "not_required", "sync_queue": {"pending": 0, "failed": 0}}


def _group_platform_providers(platform_models: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for model in platform_models:
        provider_name = str(model.get("owned_by") or "platform")
        current = grouped.setdefault(
            provider_name,
            {
                "name": provider_name,
                "route_policy": "managed",
                "http_enabled": True,
                "cli_enabled": False,
                "chat_capable": True,
                "stream_capable": True,
                "model_count": 0,
            },
        )
        current["model_count"] = int(current["model_count"]) + 1
    return list(grouped.values())
