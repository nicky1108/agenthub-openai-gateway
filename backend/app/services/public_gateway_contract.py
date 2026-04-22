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


def workspace_id_for_record(account: AccountRecord) -> str:
    return account.public_workspace_id or workspace_id_for_account(account.id)


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


@dataclass(frozen=True, slots=True)
class PublicGatewayAccountMirror:
    id: str
    workspace_id: str
    name: str
    email: str | None
    status: str


@dataclass(frozen=True, slots=True)
class PublicGatewayApiKeyMirror:
    id: str
    account_id: str
    name: str
    key_prefix: str
    secret_hash: str
    status: str
    per_minute: int | None
    per_hour: int | None
    per_day: int | None


@dataclass(frozen=True, slots=True)
class PublicGatewayMirrorApiKeyStatus:
    public_api_key_id: str
    local_api_key_id: str
    name: str
    key_prefix: str
    status: str


@dataclass(frozen=True, slots=True)
class PublicGatewayAccountMirrorStatus:
    public_account_id: str
    workspace_id: str
    local_account_id: str
    email: str | None
    status: str
    api_keys: list[PublicGatewayMirrorApiKeyStatus]


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
            account_id=account.public_account_id or str(account.id),
            workspace_id=workspace_id_for_record(account),
            api_key_id=api_key.public_api_key_id or str(api_key.id),
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
        if api_key is None:
            api_key = await session.scalar(select(ApiKeyRecord).where(ApiKeyRecord.public_api_key_id == str(event.api_key_id)))
        if account is None:
            account = await session.scalar(select(AccountRecord).where(AccountRecord.public_account_id == str(event.account_id)))
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

    async def upsert_account_mirror(
        self,
        session: AsyncSession,
        mirror: PublicGatewayAccountMirror,
    ) -> AccountRecord:
        account = await session.scalar(
            select(AccountRecord).where(AccountRecord.public_account_id == mirror.id)
        )
        if account is None:
            account = AccountRecord(
                name=mirror.name,
                email=mirror.email,
                public_account_id=mirror.id,
                public_workspace_id=mirror.workspace_id,
                status=mirror.status,
            )
            session.add(account)
        else:
            account.name = mirror.name
            account.email = mirror.email
            account.public_workspace_id = mirror.workspace_id
            account.status = mirror.status
        await session.commit()
        await session.refresh(account)
        return account

    async def upsert_api_key_mirror(
        self,
        session: AsyncSession,
        mirror: PublicGatewayApiKeyMirror,
    ) -> ApiKeyRecord:
        account = await session.scalar(
            select(AccountRecord).where(AccountRecord.public_account_id == mirror.account_id)
        )
        if account is None:
            raise LookupError("account not found")

        api_key = await session.scalar(
            select(ApiKeyRecord).where(ApiKeyRecord.public_api_key_id == mirror.id)
        )
        if api_key is None:
            api_key = ApiKeyRecord(
                account_id=account.id,
                public_api_key_id=mirror.id,
                name=mirror.name,
                key_prefix=mirror.key_prefix,
                secret_hash=mirror.secret_hash,
                status=mirror.status,
                per_minute=mirror.per_minute,
                per_hour=mirror.per_hour,
                per_day=mirror.per_day,
            )
            session.add(api_key)
        else:
            api_key.account_id = account.id
            api_key.name = mirror.name
            api_key.key_prefix = mirror.key_prefix
            api_key.secret_hash = mirror.secret_hash
            api_key.status = mirror.status
            api_key.per_minute = mirror.per_minute
            api_key.per_hour = mirror.per_hour
            api_key.per_day = mirror.per_day
        await session.commit()
        await session.refresh(api_key)
        return api_key

    async def revoke_api_key_mirror(
        self,
        session: AsyncSession,
        public_api_key_id: str,
    ) -> ApiKeyRecord:
        api_key = await session.scalar(
            select(ApiKeyRecord).where(ApiKeyRecord.public_api_key_id == public_api_key_id)
        )
        if api_key is None:
            raise LookupError("api key not found")
        api_key.status = "revoked"
        api_key.revoked_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(api_key)
        return api_key

    async def get_account_mirror_status(
        self,
        session: AsyncSession,
        public_account_id: str,
    ) -> PublicGatewayAccountMirrorStatus:
        account = await session.scalar(
            select(AccountRecord).where(AccountRecord.public_account_id == public_account_id)
        )
        if account is None:
            raise LookupError("account not found")

        api_keys = list(
            await session.scalars(
                select(ApiKeyRecord)
                .where(ApiKeyRecord.account_id == account.id)
                .order_by(ApiKeyRecord.id.asc())
            )
        )
        return PublicGatewayAccountMirrorStatus(
            public_account_id=account.public_account_id or str(account.id),
            workspace_id=workspace_id_for_record(account),
            local_account_id=str(account.id),
            email=account.email,
            status=account.status,
            api_keys=[
                PublicGatewayMirrorApiKeyStatus(
                    public_api_key_id=api_key.public_api_key_id or str(api_key.id),
                    local_api_key_id=str(api_key.id),
                    name=api_key.name,
                    key_prefix=api_key.key_prefix,
                    status=api_key.status,
                )
                for api_key in api_keys
            ],
        )


public_gateway_contract_service = PublicGatewayContractService()
