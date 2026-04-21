from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import hash_api_key
from app.core.models import AccountRecord, ApiKeyRecord, UsageRecord
from app.registry.service import ProviderRegistry


def workspace_id_for_account(account_id: int) -> str:
    return f"ws_test_account_{account_id}"


@dataclass(frozen=True, slots=True)
class PublicGatewayApiKeyIdentity:
    account_id: str
    workspace_id: str
    api_key_id: str
    status: str


@dataclass(frozen=True, slots=True)
class PublicGatewayUsageEvent:
    account_id: int
    api_key_id: int
    workspace_id: str
    provider_name: str | None
    model_id: str | None
    source: str
    billable: bool
    credits_delta: int
    outcome: str


class PublicGatewayContractService:
    def __init__(self) -> None:
        self.registry = ProviderRegistry()

    async def introspect_api_key(
        self,
        session: AsyncSession,
        token: str,
    ) -> PublicGatewayApiKeyIdentity | None:
        if not token.startswith("agk_"):
            return None

        try:
            _, prefix, _ = token.split("_", 2)
        except ValueError:
            return None

        api_key = await session.scalar(select(ApiKeyRecord).where(ApiKeyRecord.key_prefix == prefix))
        if api_key is None or api_key.secret_hash != hash_api_key(token):
            return None

        account = await session.scalar(select(AccountRecord).where(AccountRecord.id == api_key.account_id))
        if account is None:
            return None

        status = api_key.status if account.status == "active" else "inactive"
        return PublicGatewayApiKeyIdentity(
            account_id=str(account.id),
            workspace_id=workspace_id_for_account(account.id),
            api_key_id=str(api_key.id),
            status=status,
        )

    async def list_platform_models(self, session: AsyncSession) -> dict[str, object]:
        return {"object": "list", "data": await self.registry.list_public_models(session)}

    async def record_usage_event(
        self,
        session: AsyncSession,
        event: PublicGatewayUsageEvent,
    ) -> None:
        api_key = await session.scalar(select(ApiKeyRecord).where(ApiKeyRecord.id == event.api_key_id))
        account = await session.scalar(select(AccountRecord).where(AccountRecord.id == event.account_id))
        if api_key is None or account is None or api_key.account_id != account.id:
            raise LookupError("account or api key not found")

        usage = UsageRecord(
            account_id=account.id,
            api_key_id=api_key.id,
            provider_name=event.provider_name,
            model_id=event.model_id,
            outcome=event.outcome,
            usd_amount=0.0,
            credits_charged=event.credits_delta,
            pricing_source=event.source,
            token_source=event.source,
        )
        session.add(usage)
        api_key.last_used_at = datetime.now(timezone.utc)
        await session.commit()


public_gateway_contract_service = PublicGatewayContractService()
