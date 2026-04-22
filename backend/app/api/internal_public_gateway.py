from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.settings import Settings
from app.services.public_gateway_contract import (
    PublicGatewayAccountMirror,
    PublicGatewayApiKeyMirror,
    PublicGatewayUsageEvent,
    public_gateway_contract_service,
    workspace_id_for_account,
    workspace_id_for_record,
)


router = APIRouter(prefix="/internal/public-gateway", tags=["internal-public-gateway"])


class PublicGatewayIntrospectRequest(BaseModel):
    token: str


class PublicGatewayUsageEventCreate(BaseModel):
    account_id: str
    workspace_id: str
    api_key_id: str
    provider_name: str | None = None
    model_id: str | None = None
    source: str
    billable: bool
    credits_delta: int
    outcome: str


class PublicGatewayAccountMirrorCreate(BaseModel):
    id: str
    workspace_id: str
    name: str
    email: str | None = None
    status: str


class PublicGatewayApiKeyMirrorCreate(BaseModel):
    id: str
    account_id: str
    name: str
    key_prefix: str
    secret_hash: str
    status: str
    per_minute: int | None = None
    per_hour: int | None = None
    per_day: int | None = None


def get_settings() -> Settings:
    return Settings()


def require_public_gateway_token(
    x_public_gateway_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if x_public_gateway_token != settings.public_gateway_service_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid public gateway token",
        )


@router.post("/introspect-key")
async def introspect_api_key(
    payload: PublicGatewayIntrospectRequest,
    _: None = Depends(require_public_gateway_token),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    identity = await public_gateway_contract_service.introspect_api_key(session, payload.token)
    if identity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="api key not found")
    return {
        "account_id": identity.account_id,
        "workspace_id": identity.workspace_id,
        "api_key_id": identity.api_key_id,
        "status": identity.status,
    }


@router.get("/models")
async def list_platform_models(
    _: None = Depends(require_public_gateway_token),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    return await public_gateway_contract_service.list_platform_models(session)


@router.post("/usage-events", status_code=status.HTTP_202_ACCEPTED)
async def record_usage_event(
    payload: PublicGatewayUsageEventCreate,
    _: None = Depends(require_public_gateway_token),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    account_id = int(payload.account_id)
    api_key_id = int(payload.api_key_id)
    expected_workspace = workspace_id_for_account(account_id)
    if payload.workspace_id != expected_workspace:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="workspace mismatch")
    try:
        await public_gateway_contract_service.record_usage_event(
            session,
            PublicGatewayUsageEvent(
                account_id=account_id,
                api_key_id=api_key_id,
                workspace_id=payload.workspace_id,
                provider_name=payload.provider_name,
                model_id=payload.model_id,
                source=payload.source,
                billable=payload.billable,
                credits_delta=payload.credits_delta,
                outcome=payload.outcome,
            ),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account or api key not found") from exc
    return {"status": "accepted"}


@router.post("/accounts/upsert")
async def upsert_account_mirror(
    payload: PublicGatewayAccountMirrorCreate,
    _: None = Depends(require_public_gateway_token),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    account = await public_gateway_contract_service.upsert_account_mirror(
        session,
        PublicGatewayAccountMirror(
            id=payload.id,
            workspace_id=payload.workspace_id,
            name=payload.name,
            email=payload.email,
            status=payload.status,
        ),
    )
    return {
        "status": "synced",
        "account_id": account.public_account_id or str(account.id),
        "workspace_id": workspace_id_for_record(account),
    }


@router.get("/accounts/{account_id}/mirror")
async def get_account_mirror_status(
    account_id: str,
    _: None = Depends(require_public_gateway_token),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    try:
        mirror = await public_gateway_contract_service.get_account_mirror_status(session, account_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found") from exc
    return {
        "public_account_id": mirror.public_account_id,
        "workspace_id": mirror.workspace_id,
        "local_account_id": mirror.local_account_id,
        "email": mirror.email,
        "status": mirror.status,
        "api_keys": [
            {
                "public_api_key_id": api_key.public_api_key_id,
                "local_api_key_id": api_key.local_api_key_id,
                "name": api_key.name,
                "key_prefix": api_key.key_prefix,
                "status": api_key.status,
            }
            for api_key in mirror.api_keys
        ],
    }


@router.post("/api-keys/upsert")
async def upsert_api_key_mirror(
    payload: PublicGatewayApiKeyMirrorCreate,
    _: None = Depends(require_public_gateway_token),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    api_key = await public_gateway_contract_service.upsert_api_key_mirror(
        session,
        PublicGatewayApiKeyMirror(
            id=payload.id,
            account_id=payload.account_id,
            name=payload.name,
            key_prefix=payload.key_prefix,
            secret_hash=payload.secret_hash,
            status=payload.status,
            per_minute=payload.per_minute,
            per_hour=payload.per_hour,
            per_day=payload.per_day,
        ),
    )
    return {"status": "synced", "api_key_id": api_key.public_api_key_id or str(api_key.id)}


@router.post("/api-keys/revoke")
async def revoke_api_key_mirror(
    payload: PublicGatewayApiKeyMirrorCreate,
    _: None = Depends(require_public_gateway_token),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    api_key = await public_gateway_contract_service.revoke_api_key_mirror(session, payload.id)
    return {"status": "revoked", "api_key_id": api_key.public_api_key_id or str(api_key.id)}
