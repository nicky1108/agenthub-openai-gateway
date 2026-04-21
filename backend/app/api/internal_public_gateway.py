from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.settings import Settings
from app.services.public_gateway_contract import (
    PublicGatewayUsageEvent,
    public_gateway_contract_service,
    workspace_id_for_account,
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
