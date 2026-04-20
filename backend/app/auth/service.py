from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.models import AccountRecord, ApiKeyRecord, UsageRecord


def generate_api_key() -> tuple[str, str]:
    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(24)
    token = f"agk_{prefix}_{secret}"
    return prefix, token


def hash_api_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class AuthContext:
    account: AccountRecord
    api_key: ApiKeyRecord
    token: str


class ApiKeyAuthService:
    async def authenticate(
        self,
        session: AsyncSession,
        authorization: str | None,
    ) -> AuthContext:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing bearer token",
            )

        token = authorization.removeprefix("Bearer ").strip()
        if not token.startswith("agk_"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid api key",
            )

        try:
            _, prefix, _ = token.split("_", 2)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid api key",
            ) from exc

        api_key = await session.scalar(select(ApiKeyRecord).where(ApiKeyRecord.key_prefix == prefix))
        if api_key is None or api_key.secret_hash != hash_api_key(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid api key",
            )
        if api_key.status != "active":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="api key is not active",
            )

        account = await session.scalar(select(AccountRecord).where(AccountRecord.id == api_key.account_id))
        if account is None or account.status != "active":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="account is not active",
            )

        return AuthContext(account=account, api_key=api_key, token=token)

    async def enforce_limits(
        self,
        session: AsyncSession,
        context: AuthContext,
    ) -> None:
        now = datetime.now(timezone.utc)
        windows = [
            ("minute", context.api_key.per_minute, now - timedelta(minutes=1)),
            ("hour", context.api_key.per_hour, now - timedelta(hours=1)),
            ("day", context.api_key.per_day, now - timedelta(days=1)),
        ]
        for label, limit, since in windows:
            if limit is None:
                continue
            count = await session.scalar(
                select(func.count(UsageRecord.id)).where(
                    UsageRecord.api_key_id == context.api_key.id,
                    UsageRecord.created_at >= since,
                    UsageRecord.outcome.in_(("success", "error", "limited")),
                )
            )
            if count is not None and count >= limit:
                await self.record_usage(session, context, None, None, "limited")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"{label} rate limit exceeded",
                )

    async def record_usage(
        self,
        session: AsyncSession,
        context: AuthContext,
        provider_name: str | None,
        model_id: str | None,
        outcome: str,
    ) -> None:
        usage = UsageRecord(
            account_id=context.account.id,
            api_key_id=context.api_key.id,
            provider_name=provider_name,
            model_id=model_id,
            outcome=outcome,
        )
        session.add(usage)
        context.api_key.last_used_at = datetime.now(timezone.utc)
        await session.commit()


auth_service = ApiKeyAuthService()


async def require_api_key(
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> AuthContext:
    context = await auth_service.authenticate(session, authorization)
    await auth_service.enforce_limits(session, context)
    return context
