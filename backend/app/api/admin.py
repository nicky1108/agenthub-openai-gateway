from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, model_validator, field_validator
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.admins import account_is_named_admin
from app.auth.service import generate_api_key, hash_api_key
from app.billing.service import billing_service
from app.discovery.service import ProviderDiscoveryService
from app.core.db import get_session
from app.core.models import (
    AccountRecord,
    AuthSessionRecord,
    ApiKeyRecord,
    CreditLedgerRecord,
    ModelPricingRecord,
    ProviderModelRecord,
    ProviderRecord,
    UsageRecord,
)
from app.core.secrets import seal_secret
from app.pricing.service import OfficialPricingService
from app.orchestration.chat import ChatOrchestrator
from app.core.settings import Settings
from app.registry.service import ProviderNotFoundError
from app.services.custom_provider_runtime import summarize_provider_error_response

router = APIRouter(prefix="/admin", tags=["admin"])
discovery = ProviderDiscoveryService()
pricing = OfficialPricingService()
chat_orchestrator = ChatOrchestrator()


class ProviderCreate(BaseModel):
    name: str
    exposed_model: str = "default"
    http_enabled: bool
    cli_enabled: bool
    route_policy: str
    chat_capable: bool = True
    stream_capable: bool = True
    http_base_url: str | None = None
    http_api_key: str | None = None
    http_headers_json: str = "{}"
    cli_command: str | None = None
    cli_args_json: str = "[]"
    cli_env_json: str = "{}"
    cli_cwd: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if ":" in value:
            raise ValueError("must not contain ':'")
        return value

    @model_validator(mode="after")
    def validate_transport_requirements(self) -> "ProviderCreate":
        if self.http_enabled and not self.http_base_url:
            raise ValueError("http_base_url is required when http_enabled is true")
        if self.cli_enabled and not self.cli_command:
            raise ValueError("cli_command is required when cli_enabled is true")
        return self


class ProviderPatch(BaseModel):
    exposed_model: str | None = None
    http_enabled: bool | None = None
    cli_enabled: bool | None = None
    route_policy: str | None = None
    chat_capable: bool | None = None
    stream_capable: bool | None = None
    http_base_url: str | None = None
    http_api_key: str | None = None
    http_headers_json: str | None = None
    cli_command: str | None = None
    cli_args_json: str | None = None
    cli_env_json: str | None = None
    cli_cwd: str | None = None


class ProviderRead(BaseModel):
    id: int
    name: str
    exposed_model: str = "default"
    http_enabled: bool
    cli_enabled: bool
    route_policy: str
    chat_capable: bool = True
    stream_capable: bool = True
    http_base_url: str | None = None
    http_api_key: str | None = None
    http_api_key_configured: bool = False
    http_headers_json: str = "{}"
    http_headers_configured: bool = False
    cli_command: str | None = None
    cli_args_json: str = "[]"
    cli_env_json: str = "{}"
    cli_env_configured: bool = False
    cli_cwd: str | None = None


class ProviderHealth(BaseModel):
    name: str
    route_policy: str
    capabilities: dict[str, bool]


class ModelPricingRead(BaseModel):
    provider_name: str
    native_model: str
    source_kind: str
    source_url: str
    source_label: str
    currency: str
    unit: str
    input_price: float | None = None
    cached_input_price: float | None = None
    output_price: float | None = None
    input_price_high: float | None = None
    cached_input_price_high: float | None = None
    output_price_high: float | None = None
    high_price_threshold_tokens: int | None = None
    notes: str | None = None
    synced_at: str


class ProviderModelRead(BaseModel):
    id: int
    native_model: str
    exposed_model_id: str
    source: str
    enabled: bool
    manually_overridden: bool
    pricing: ModelPricingRead | None = None


class ProviderModelPatch(BaseModel):
    exposed_model_id: str | None = None
    enabled: bool | None = None


class ProviderModelCreate(BaseModel):
    native_model: str
    exposed_model_id: str
    enabled: bool = True


class PricingOverridePatch(BaseModel):
    input_price: float | None = None
    cached_input_price: float | None = None
    output_price: float | None = None
    input_price_high: float | None = None
    cached_input_price_high: float | None = None
    output_price_high: float | None = None
    high_price_threshold_tokens: int | None = None
    notes: str | None = None


def normalize_optional_email(value: str | None) -> str | None:
    if value is None:
        return None
    email = value.strip()
    if not email:
        return None
    if " " in email or email.count("@") != 1:
        raise ValueError("invalid email address")
    local_part, domain = email.split("@", 1)
    if not local_part or not domain or "." not in domain:
        raise ValueError("invalid email address")
    if domain.startswith(".") or domain.endswith(".") or ".." in domain:
        raise ValueError("invalid email address")
    return email


class AccountCreate(BaseModel):
    name: str
    email: str | None = None
    is_admin: bool = False
    public_account_id: str | None = None
    public_workspace_id: str | None = None
    notes: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        return normalize_optional_email(value)


class AccountUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    status: str | None = None
    is_admin: bool | None = None
    public_account_id: str | None = None
    public_workspace_id: str | None = None
    notes: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        return normalize_optional_email(value)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        status_value = value.strip().lower()
        if status_value not in {"active", "suspended", "deleted"}:
            raise ValueError("must be active, suspended, or deleted")
        return status_value


class AccountRead(BaseModel):
    id: int
    name: str
    email: str | None = None
    status: str
    is_admin: bool
    credit_balance: float
    public_account_id: str | None = None
    public_workspace_id: str | None = None
    notes: str | None = None
    created_at: str | None = None


class AccountSyncSummary(BaseModel):
    total_accounts: int
    mirrored_accounts: int
    accounts_needing_backfill: int
    accounts_with_pending_sync: int
    accounts_with_failed_sync: int
    accounts_fully_converged: int


class CreditAdjustmentCreate(BaseModel):
    credits_delta: float
    notes: str | None = None


class CreditLedgerRead(BaseModel):
    id: int
    account_id: int
    api_key_id: int | None = None
    usage_record_id: int | None = None
    entry_type: str
    credits_delta: float
    balance_after: float
    usd_amount: float | None = None
    provider_name: str | None = None
    model_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    pricing_source: str | None = None
    notes: str | None = None
    created_at: str


class CreditLedgerPage(BaseModel):
    items: list[CreditLedgerRead]
    total: int
    limit: int
    offset: int


class ApiKeyCreate(BaseModel):
    account_id: int
    name: str
    per_minute: int | None = None
    per_hour: int | None = None
    per_day: int | None = None


class ApiKeyUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    per_minute: int | None = None
    per_hour: int | None = None
    per_day: int | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        status_value = value.strip().lower()
        if status_value not in {"active", "revoked"}:
            raise ValueError("must be active or revoked")
        return status_value


class ApiKeyRead(BaseModel):
    id: int
    account_id: int
    name: str
    key_prefix: str
    status: str
    per_minute: int | None = None
    per_hour: int | None = None
    per_day: int | None = None
    last_used_at: str | None = None


class ApiKeyCreated(ApiKeyRead):
    api_key: str


class UsageSummary(BaseModel):
    account_id: int
    api_key_id: int
    total_requests: int
    limited_requests: int
    by_provider: dict[str, int]
    by_model: dict[str, int]


class UsageActivityKey(BaseModel):
    api_key_id: int
    account_id: int
    name: str
    key_prefix: str
    status: str
    last_used_at: str | None = None
    total_requests: int
    limited_requests: int


class UsageRecordRead(BaseModel):
    id: int
    account_id: int
    account_name: str | None = None
    api_key_id: int
    api_key_name: str | None = None
    key_prefix: str | None = None
    provider_name: str | None = None
    model_id: str | None = None
    outcome: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    usd_amount: float | None = None
    credits_charged: float | None = None
    pricing_source: str | None = None
    token_source: str | None = None
    created_at: str


class UsageRecordsPage(BaseModel):
    items: list[UsageRecordRead]
    total: int
    limit: int
    offset: int


class UsageOverview(BaseModel):
    key_activity: list[UsageActivityKey]
    by_provider: dict[str, int]
    by_model: dict[str, int]


class DashboardSummary(BaseModel):
    total_requests: int
    active_api_keys: int
    error_rate: float
    rate_limit_hits: int


class DashboardTimeseriesBucket(BaseModel):
    label: str
    start_at: str
    total_requests: int
    error_requests: int
    limited_requests: int


class DashboardTimeseries(BaseModel):
    window: Literal["24h", "7d"]
    buckets: list[DashboardTimeseriesBucket]


class SettingsOverview(BaseModel):
    gateway_host: str
    gateway_port: int
    frontend_base_url: str
    database_scheme: str
    email_password_enabled: bool
    github_oauth_enabled: bool
    google_oauth_enabled: bool
    admin_secret_configured: bool


class AdminTestChatCreate(BaseModel):
    model: str
    messages: list[dict[str, object]]
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


def compact_error_detail(value: str | None) -> str | None:
    if not value:
        return None
    compacted = " ".join(value.split())
    return compacted[:240] if compacted else None


def admin_test_chat_provider_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, httpx.HTTPStatusError):
        detail = f"provider returned {exc.response.status_code}"
        provider_detail = summarize_provider_error_response(exc.response)
        if provider_detail:
            detail = f"{detail}: {provider_detail}"
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
    if isinstance(exc, httpx.HTTPError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="provider request failed")
    if isinstance(exc, TimeoutError):
        return HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="provider request timed out")

    detail = compact_error_detail(str(exc))
    message = "provider runtime failed"
    if detail:
        message = f"{message}: {detail}"
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message)


def get_settings() -> Settings:
    return Settings()


async def require_admin(
    x_admin_secret: str | None = Header(default=None),
    agh_session: str | None = Cookie(default=None, alias="agh_session"),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> None:
    if settings.admin_emails:
        if not agh_session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid admin credentials",
            )
        session_record = await session.scalar(
            select(AuthSessionRecord).where(
                AuthSessionRecord.session_token_hash == hash_api_key(agh_session),
                AuthSessionRecord.status == "active",
                AuthSessionRecord.expires_at > datetime.now(timezone.utc),
            )
        )
        if session_record is not None:
            account = await session.get(AccountRecord, session_record.account_id)
            if account_is_named_admin(account, settings):
                return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid admin credentials",
        )

    if x_admin_secret and x_admin_secret == settings.admin_secret:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid admin credentials",
    )


def normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def serialize_account(account: AccountRecord, settings: Settings) -> AccountRead:
    return AccountRead(
        id=account.id,
        name=account.name,
        email=account.email,
        status=account.status,
        is_admin=account_is_named_admin(account, settings),
        credit_balance=account.credit_balance,
        public_account_id=account.public_account_id,
        public_workspace_id=account.public_workspace_id,
        notes=account.notes,
        created_at=account.created_at.isoformat() if account.created_at else None,
    )


def serialize_api_key(row: ApiKeyRecord) -> ApiKeyRead:
    return ApiKeyRead(
        id=row.id,
        account_id=row.account_id,
        name=row.name,
        key_prefix=row.key_prefix,
        status=row.status,
        per_minute=row.per_minute,
        per_hour=row.per_hour,
        per_day=row.per_day,
        last_used_at=row.last_used_at.isoformat() if row.last_used_at else None,
    )


def serialize_usage_record(
    row: UsageRecord,
    accounts_by_id: dict[int, AccountRecord],
    api_keys_by_id: dict[int, ApiKeyRecord],
) -> UsageRecordRead:
    account = accounts_by_id.get(row.account_id)
    api_key = api_keys_by_id.get(row.api_key_id)
    return UsageRecordRead(
        id=row.id,
        account_id=row.account_id,
        account_name=account.name if account else None,
        api_key_id=row.api_key_id,
        api_key_name=api_key.name if api_key else None,
        key_prefix=api_key.key_prefix if api_key else None,
        provider_name=row.provider_name,
        model_id=row.model_id,
        outcome=row.outcome,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        cached_input_tokens=row.cached_input_tokens,
        usd_amount=row.usd_amount,
        credits_charged=row.credits_charged,
        pricing_source=row.pricing_source,
        token_source=row.token_source,
        created_at=normalize_timestamp(row.created_at).isoformat(),
    )


def validate_provider_transport(record: ProviderRecord) -> None:
    if record.http_enabled and not record.http_base_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="http_base_url is required when http_enabled is true",
        )
    if record.cli_enabled and not record.cli_command:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="cli_command is required when cli_enabled is true",
        )


def _secret_configured(value: str | None, *, empty_value: str | None = None) -> bool:
    if not value:
        return False
    if empty_value is not None and value == empty_value:
        return False
    return True


def _seal_optional_secret(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return seal_secret(value)


def _seal_config_json(value: str | None, *, empty_value: str) -> str:
    if value is None or not value.strip():
        return empty_value
    return seal_secret(value) if value != empty_value else empty_value


def serialize_provider(record: ProviderRecord) -> ProviderRead:
    return ProviderRead(
        id=record.id,
        name=record.name,
        exposed_model=record.exposed_model,
        http_enabled=record.http_enabled,
        cli_enabled=record.cli_enabled,
        route_policy=record.route_policy,
        chat_capable=record.chat_capable,
        stream_capable=record.stream_capable,
        http_base_url=record.http_base_url,
        http_api_key=None,
        http_api_key_configured=_secret_configured(record.http_api_key),
        http_headers_json="{}",
        http_headers_configured=_secret_configured(record.http_headers_json, empty_value="{}"),
        cli_command=record.cli_command,
        cli_args_json=record.cli_args_json,
        cli_env_json="{}",
        cli_env_configured=_secret_configured(record.cli_env_json, empty_value="{}"),
        cli_cwd=record.cli_cwd,
    )


def _cli_command_allowed(command: str, allowlist: set[str]) -> bool:
    if not allowlist:
        return True
    command_name = Path(command).name
    return command in allowlist or command_name in allowlist


def validate_admin_cli_management(record: ProviderRecord, settings: Settings) -> None:
    if not record.cli_enabled and not record.cli_command:
        return
    if settings.is_production and not settings.admin_cli_provider_management_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CLI provider management is disabled",
        )
    if (
        settings.is_production
        and record.cli_command
        and not _cli_command_allowed(record.cli_command, settings.admin_cli_provider_command_allowlist)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="cli_command is not allowlisted",
        )


def build_timeseries_window(window: Literal["24h", "7d"]) -> tuple[list[datetime], list[str], timedelta]:
    now = datetime.now(timezone.utc)
    if window == "24h":
        anchor = now.replace(minute=0, second=0, microsecond=0)
        starts = [anchor - timedelta(hours=index) for index in range(23, -1, -1)]
        labels = [start.strftime("%H:00") for start in starts]
        return starts, labels, timedelta(hours=1)

    anchor = now.replace(hour=0, minute=0, second=0, microsecond=0)
    starts = [anchor - timedelta(days=index) for index in range(6, -1, -1)]
    labels = [start.strftime("%b %d") for start in starts]
    return starts, labels, timedelta(days=1)


@router.post("/providers", response_model=ProviderRead, status_code=status.HTTP_201_CREATED)
async def create_provider(
    payload: ProviderCreate,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ProviderRead:
    record_payload = payload.model_dump()
    if record_payload["exposed_model"] == "default":
        if record_payload["name"] == "codex":
            record_payload["exposed_model"] = "gpt-5.4"
        elif record_payload["name"] == "gemini":
            record_payload["exposed_model"] = "gemini-2.5-pro"
    record_payload["http_api_key"] = _seal_optional_secret(record_payload["http_api_key"])
    record_payload["http_headers_json"] = _seal_config_json(record_payload["http_headers_json"], empty_value="{}")
    record_payload["cli_env_json"] = _seal_config_json(record_payload["cli_env_json"], empty_value="{}")
    record = ProviderRecord(**record_payload)
    validate_admin_cli_management(record, settings)
    session.add(record)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="provider already exists",
        ) from exc
    await session.refresh(record)
    await discovery.sync_provider_models(session, record)
    await pricing.sync_provider_pricing(session, record.name)
    return serialize_provider(record)


@router.get("/providers", response_model=list[ProviderRead])
async def list_providers(
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ProviderRead]:
    rows = await session.scalars(select(ProviderRecord).order_by(ProviderRecord.id.asc()))
    return [serialize_provider(row) for row in rows]


@router.patch("/providers/{provider_name}", response_model=ProviderRead)
async def update_provider(
    provider_name: str,
    payload: ProviderPatch,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ProviderRead:
    record = await session.scalar(select(ProviderRecord).where(ProviderRecord.name == provider_name))
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="provider not found")

    fields = payload.model_fields_set
    if "exposed_model" in fields and payload.exposed_model is not None:
        record.exposed_model = payload.exposed_model
    if "http_enabled" in fields and payload.http_enabled is not None:
        record.http_enabled = payload.http_enabled
    if "cli_enabled" in fields and payload.cli_enabled is not None:
        record.cli_enabled = payload.cli_enabled
    if "route_policy" in fields and payload.route_policy is not None:
        record.route_policy = payload.route_policy
    if "chat_capable" in fields and payload.chat_capable is not None:
        record.chat_capable = payload.chat_capable
    if "stream_capable" in fields and payload.stream_capable is not None:
        record.stream_capable = payload.stream_capable
    if "http_base_url" in fields:
        record.http_base_url = payload.http_base_url
    if "http_api_key" in fields:
        record.http_api_key = _seal_optional_secret(payload.http_api_key)
    if "http_headers_json" in fields and payload.http_headers_json is not None:
        record.http_headers_json = _seal_config_json(payload.http_headers_json, empty_value="{}")
    if "cli_command" in fields:
        record.cli_command = payload.cli_command
    if "cli_args_json" in fields and payload.cli_args_json is not None:
        record.cli_args_json = payload.cli_args_json
    if "cli_env_json" in fields and payload.cli_env_json is not None:
        record.cli_env_json = _seal_config_json(payload.cli_env_json, empty_value="{}")
    if "cli_cwd" in fields:
        record.cli_cwd = payload.cli_cwd

    validate_provider_transport(record)
    validate_admin_cli_management(record, settings)
    await session.commit()
    await session.refresh(record)
    return serialize_provider(record)


@router.delete("/providers/{provider_name}", response_model=ProviderRead)
async def delete_provider(
    provider_name: str,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ProviderRead:
    record = await session.scalar(select(ProviderRecord).where(ProviderRecord.name == provider_name))
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="provider not found")
    payload = serialize_provider(record)

    model_rows = list(
        await session.scalars(select(ProviderModelRecord).where(ProviderModelRecord.provider_id == record.id))
    )
    pricing_rows = list(
        await session.scalars(select(ModelPricingRecord).where(ModelPricingRecord.provider_name == record.name))
    )
    for row in model_rows:
        await session.delete(row)
    for row in pricing_rows:
        await session.delete(row)
    await session.delete(record)
    await session.commit()
    return payload


@router.get("/health", response_model=list[ProviderHealth])
async def list_health(
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ProviderHealth]:
    rows = await session.scalars(select(ProviderRecord).order_by(ProviderRecord.id.asc()))
    return [
        ProviderHealth(
            name=row.name,
            route_policy=row.route_policy,
            capabilities={
                "chat": row.chat_capable,
                "stream": row.stream_capable,
                "http": row.http_enabled,
                "cli": row.cli_enabled,
            },
        )
        for row in rows
    ]


@router.post("/accounts", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AccountRead:
    account = AccountRecord(
        name=payload.name.strip(),
        email=payload.email,
        is_admin=payload.is_admin,
        public_account_id=payload.public_account_id,
        public_workspace_id=payload.public_workspace_id,
        notes=payload.notes,
    )
    session.add(account)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="account already exists") from exc
    await session.refresh(account)
    return serialize_account(account, settings)


@router.get("/accounts", response_model=list[AccountRead])
async def list_accounts(
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[AccountRead]:
    rows = await session.scalars(select(AccountRecord).order_by(AccountRecord.id.asc()))
    return [serialize_account(row, settings) for row in rows]


@router.patch("/accounts/{account_id}", response_model=AccountRead)
async def update_account(
    account_id: int,
    payload: AccountUpdate,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AccountRead:
    account = await session.scalar(select(AccountRecord).where(AccountRecord.id == account_id))
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")

    if payload.name is not None:
        stripped_name = payload.name.strip()
        if not stripped_name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="account name is required")
        account.name = stripped_name
    if payload.email is not None:
        account.email = payload.email
    if payload.status is not None:
        account.status = payload.status
    if payload.is_admin is not None:
        account.is_admin = payload.is_admin
    if payload.public_account_id is not None:
        account.public_account_id = payload.public_account_id.strip() or None
    if payload.public_workspace_id is not None:
        account.public_workspace_id = payload.public_workspace_id.strip() or None
    if payload.notes is not None:
        account.notes = payload.notes

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="account already exists") from exc
    await session.refresh(account)
    return serialize_account(account, settings)


@router.delete("/accounts/{account_id}", response_model=AccountRead)
async def delete_account(
    account_id: int,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AccountRead:
    account = await session.scalar(select(AccountRecord).where(AccountRecord.id == account_id))
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
    account.status = "deleted"
    await session.commit()
    await session.refresh(account)
    return serialize_account(account, settings)


@router.get("/account-sync/summary", response_model=AccountSyncSummary)
async def account_sync_summary(
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AccountSyncSummary:
    total_accounts = await session.scalar(select(func.count(AccountRecord.id))) or 0
    mirrored_accounts = (
        await session.scalar(
            select(func.count(AccountRecord.id)).where(
                (AccountRecord.public_account_id.is_not(None))
                | (AccountRecord.public_workspace_id.is_not(None))
            )
        )
    ) or 0
    accounts_needing_backfill = max(total_accounts - mirrored_accounts, 0)
    return AccountSyncSummary(
        total_accounts=total_accounts,
        mirrored_accounts=mirrored_accounts,
        accounts_needing_backfill=accounts_needing_backfill,
        accounts_with_pending_sync=0,
        accounts_with_failed_sync=0,
        accounts_fully_converged=mirrored_accounts,
    )


@router.post("/accounts/{account_id}/credits/adjust", response_model=AccountRead)
async def adjust_account_credits(
    account_id: int,
    payload: CreditAdjustmentCreate,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AccountRead:
    account = await session.scalar(select(AccountRecord).where(AccountRecord.id == account_id))
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
    await billing_service.record_manual_adjustment(session, account, payload.credits_delta, payload.notes)
    await session.refresh(account)
    return serialize_account(account, settings)


@router.get("/accounts/{account_id}/credits/ledger", response_model=CreditLedgerPage)
async def list_account_credit_ledger(
    account_id: int,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CreditLedgerPage:
    total = (
        await session.scalar(
            select(func.count(CreditLedgerRecord.id)).where(CreditLedgerRecord.account_id == account_id)
        )
    ) or 0
    rows = list(
        await session.scalars(
            select(CreditLedgerRecord)
            .where(CreditLedgerRecord.account_id == account_id)
            .order_by(CreditLedgerRecord.created_at.desc(), CreditLedgerRecord.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return CreditLedgerPage(
        items=[
            CreditLedgerRead(
                id=row.id,
                account_id=row.account_id,
                api_key_id=row.api_key_id,
                usage_record_id=row.usage_record_id,
                entry_type=row.entry_type,
                credits_delta=row.credits_delta,
                balance_after=row.balance_after,
                usd_amount=row.usd_amount,
                provider_name=row.provider_name,
                model_id=row.model_id,
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
                cached_input_tokens=row.cached_input_tokens,
                pricing_source=row.pricing_source,
                notes=row.notes,
                created_at=row.created_at.isoformat(),
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyCreated:
    account = await session.scalar(select(AccountRecord).where(AccountRecord.id == payload.account_id))
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
    prefix, token = generate_api_key()
    record = ApiKeyRecord(
        account_id=payload.account_id,
        name=payload.name,
        key_prefix=prefix,
        secret_hash=hash_api_key(token),
        per_minute=payload.per_minute,
        per_hour=payload.per_hour,
        per_day=payload.per_day,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return ApiKeyCreated(
        id=record.id,
        account_id=record.account_id,
        name=record.name,
        key_prefix=record.key_prefix,
        status=record.status,
        per_minute=record.per_minute,
        per_hour=record.per_hour,
        per_day=record.per_day,
        last_used_at=None,
        api_key=token,
    )


@router.get("/api-keys", response_model=list[ApiKeyRead])
async def list_api_keys(
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ApiKeyRead]:
    rows = await session.scalars(
        select(ApiKeyRecord)
        .where(ApiKeyRecord.status != "deleted")
        .order_by(ApiKeyRecord.id.asc())
    )
    return [serialize_api_key(row) for row in rows]


@router.patch("/api-keys/{key_id}", response_model=ApiKeyRead)
async def update_api_key(
    key_id: int,
    payload: ApiKeyUpdate,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyRead:
    row = await session.scalar(select(ApiKeyRecord).where(ApiKeyRecord.id == key_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="api key not found")
    fields = payload.model_fields_set
    if "name" in fields and payload.name is not None:
        stripped_name = payload.name.strip()
        if not stripped_name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="api key name is required")
        row.name = stripped_name
    if "status" in fields and payload.status is not None:
        row.status = payload.status
        if payload.status == "revoked" and row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
        if payload.status == "active":
            row.revoked_at = None
    if "per_minute" in fields:
        row.per_minute = payload.per_minute
    if "per_hour" in fields:
        row.per_hour = payload.per_hour
    if "per_day" in fields:
        row.per_day = payload.per_day
    await session.commit()
    await session.refresh(row)
    return serialize_api_key(row)


@router.post("/api-keys/{key_id}/revoke", response_model=ApiKeyRead)
async def revoke_api_key(
    key_id: int,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyRead:
    row = await session.scalar(select(ApiKeyRecord).where(ApiKeyRecord.id == key_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="api key not found")
    row.status = "revoked"
    row.revoked_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(row)
    return serialize_api_key(row)


@router.delete("/api-keys/{key_id}", response_model=ApiKeyRead)
async def delete_api_key(
    key_id: int,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyRead:
    row = await session.scalar(select(ApiKeyRecord).where(ApiKeyRecord.id == key_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="api key not found")
    row.status = "deleted"
    row.revoked_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(row)
    return serialize_api_key(row)


@router.get("/api-keys/{key_id}/usage", response_model=UsageSummary)
async def get_api_key_usage(
    key_id: int,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> UsageSummary:
    key = await session.scalar(select(ApiKeyRecord).where(ApiKeyRecord.id == key_id))
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="api key not found")
    rows = await session.scalars(select(UsageRecord).where(UsageRecord.api_key_id == key_id))
    usage_rows = list(rows)
    by_provider: dict[str, int] = {}
    by_model: dict[str, int] = {}
    for row in usage_rows:
        if row.provider_name:
            by_provider[row.provider_name] = by_provider.get(row.provider_name, 0) + 1
        if row.model_id:
            by_model[row.model_id] = by_model.get(row.model_id, 0) + 1
    return UsageSummary(
        account_id=key.account_id,
        api_key_id=key.id,
        total_requests=len(usage_rows),
        limited_requests=sum(1 for row in usage_rows if row.outcome == "limited"),
        by_provider=by_provider,
        by_model=by_model,
    )


@router.get("/usage/overview", response_model=UsageOverview)
async def get_usage_overview(
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> UsageOverview:
    usage_by_key_rows = list(
        await session.execute(
            select(
                UsageRecord.api_key_id,
                func.count(UsageRecord.id),
                func.sum(case((UsageRecord.outcome == "limited", 1), else_=0)),
            ).group_by(UsageRecord.api_key_id)
        )
    )
    usage_by_key = {
        row[0]: {"total_requests": row[1], "limited_requests": row[2] or 0}
        for row in usage_by_key_rows
        if row[0] is not None
    }
    provider_rows = list(
        await session.execute(
            select(UsageRecord.provider_name, func.count(UsageRecord.id))
            .where(UsageRecord.provider_name.is_not(None))
            .group_by(UsageRecord.provider_name)
        )
    )
    model_rows = list(
        await session.execute(
            select(UsageRecord.model_id, func.count(UsageRecord.id))
            .where(UsageRecord.model_id.is_not(None))
            .group_by(UsageRecord.model_id)
        )
    )
    api_keys = list(await session.scalars(select(ApiKeyRecord).order_by(ApiKeyRecord.id.asc())))
    key_activity = [
        UsageActivityKey(
            api_key_id=api_key.id,
            account_id=api_key.account_id,
            name=api_key.name,
            key_prefix=api_key.key_prefix,
            status=api_key.status,
            last_used_at=api_key.last_used_at.isoformat() if api_key.last_used_at else None,
            total_requests=usage_by_key.get(api_key.id, {}).get("total_requests", 0),
            limited_requests=usage_by_key.get(api_key.id, {}).get("limited_requests", 0),
        )
        for api_key in api_keys
    ]
    return UsageOverview(
        key_activity=key_activity,
        by_provider={name: count for name, count in provider_rows if name},
        by_model={name: count for name, count in model_rows if name},
    )


@router.get("/usage/records", response_model=UsageRecordsPage)
async def list_usage_records(
    account_id: int | None = Query(default=None),
    api_key_id: int | None = Query(default=None),
    outcome: str | None = Query(default=None),
    provider_name: str | None = Query(default=None),
    model_id: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> UsageRecordsPage:
    statement = select(UsageRecord)
    count_statement = select(func.count(UsageRecord.id))
    if account_id is not None:
        statement = statement.where(UsageRecord.account_id == account_id)
        count_statement = count_statement.where(UsageRecord.account_id == account_id)
    if api_key_id is not None:
        statement = statement.where(UsageRecord.api_key_id == api_key_id)
        count_statement = count_statement.where(UsageRecord.api_key_id == api_key_id)
    if outcome:
        statement = statement.where(UsageRecord.outcome == outcome)
        count_statement = count_statement.where(UsageRecord.outcome == outcome)
    if provider_name:
        statement = statement.where(UsageRecord.provider_name == provider_name)
        count_statement = count_statement.where(UsageRecord.provider_name == provider_name)
    if model_id:
        statement = statement.where(UsageRecord.model_id == model_id)
        count_statement = count_statement.where(UsageRecord.model_id == model_id)
    total = await session.scalar(count_statement) or 0
    usage_rows = list(
        await session.scalars(
            statement
            .order_by(UsageRecord.created_at.desc(), UsageRecord.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    account_ids = {row.account_id for row in usage_rows}
    api_key_ids = {row.api_key_id for row in usage_rows}
    accounts = (
        list(await session.scalars(select(AccountRecord).where(AccountRecord.id.in_(account_ids))))
        if account_ids
        else []
    )
    api_keys = (
        list(await session.scalars(select(ApiKeyRecord).where(ApiKeyRecord.id.in_(api_key_ids))))
        if api_key_ids
        else []
    )
    accounts_by_id = {row.id: row for row in accounts}
    api_keys_by_id = {row.id: row for row in api_keys}
    return UsageRecordsPage(
        items=[serialize_usage_record(row, accounts_by_id, api_keys_by_id) for row in usage_rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/dashboard/summary", response_model=DashboardSummary)
async def dashboard_summary(
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DashboardSummary:
    total = (
        await session.scalar(select(func.count(UsageRecord.id)))
    ) or 0
    error_count = (
        await session.scalar(
            select(func.count(UsageRecord.id)).where(UsageRecord.outcome == "error")
        )
    ) or 0
    limited_count = (
        await session.scalar(
            select(func.count(UsageRecord.id)).where(UsageRecord.outcome == "limited")
        )
    ) or 0
    active_key_count = (
        await session.scalar(
            select(func.count(ApiKeyRecord.id)).where(ApiKeyRecord.status == "active")
        )
    ) or 0
    return DashboardSummary(
        total_requests=total,
        active_api_keys=active_key_count,
        error_rate=(error_count / total) if total else 0.0,
        rate_limit_hits=limited_count,
    )


@router.get("/dashboard/timeseries", response_model=DashboardTimeseries)
async def dashboard_timeseries(
    window: Literal["24h", "7d"] = Query(default="24h"),
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DashboardTimeseries:
    bucket_starts, labels, bucket_size = build_timeseries_window(window)
    earliest = bucket_starts[0]
    rows = list(
        await session.scalars(
            select(UsageRecord)
            .where(UsageRecord.created_at >= earliest)
            .order_by(UsageRecord.created_at.asc())
        )
    )
    counters = [
        {"total_requests": 0, "error_requests": 0, "limited_requests": 0}
        for _ in bucket_starts
    ]

    for row in rows:
        created_at = normalize_timestamp(row.created_at)
        delta = created_at - earliest
        bucket_index = int(delta.total_seconds() // bucket_size.total_seconds())
        if bucket_index < 0 or bucket_index >= len(counters):
            continue
        counters[bucket_index]["total_requests"] += 1
        if row.outcome == "error":
            counters[bucket_index]["error_requests"] += 1
        if row.outcome == "limited":
            counters[bucket_index]["limited_requests"] += 1

    return DashboardTimeseries(
        window=window,
        buckets=[
            DashboardTimeseriesBucket(
                label=label,
                start_at=start.isoformat(),
                total_requests=counter["total_requests"],
                error_requests=counter["error_requests"],
                limited_requests=counter["limited_requests"],
            )
            for start, label, counter in zip(bucket_starts, labels, counters, strict=True)
        ],
    )


@router.get("/settings/overview", response_model=SettingsOverview)
async def settings_overview(
    _: None = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> SettingsOverview:
    return SettingsOverview(
        gateway_host=settings.openai_gateway_host,
        gateway_port=settings.openai_gateway_port,
        frontend_base_url=settings.frontend_base_url,
        database_scheme=settings.database_scheme,
        email_password_enabled=True,
        github_oauth_enabled=settings.github_oauth_enabled,
        google_oauth_enabled=settings.google_oauth_enabled,
        admin_secret_configured=bool(settings.admin_secret),
    )


@router.post("/test-chat")
async def admin_test_chat(
    payload: AdminTestChatCreate,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    provider_name, _, native_model = payload.model.partition(":")
    provider = await session.scalar(select(ProviderRecord).where(ProviderRecord.name == provider_name))
    if provider is not None:
        model_row = await session.scalar(
            select(ProviderModelRecord).where(
                ProviderModelRecord.provider_id == provider.id,
                ProviderModelRecord.native_model == native_model,
            )
        )
        if model_row is not None and not model_row.enabled:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model is disabled")

    request_payload = {
        "model": payload.model,
        "messages": payload.messages,
        "stream": payload.stream,
        "temperature": payload.temperature,
        "top_p": payload.top_p,
        "max_tokens": payload.max_tokens,
        "stop": payload.stop,
    }
    try:
        if payload.stream:
            request, provider = await chat_orchestrator.prepare(request_payload, session)
            stream = chat_orchestrator.stream_prepared(request, provider)
            try:
                first_chunk = await anext(stream)
            except StopAsyncIteration:
                first_chunk = None

            async def stream_response():
                if first_chunk is not None:
                    yield first_chunk
                async for chunk in stream:
                    yield chunk

            return StreamingResponse(stream_response(), media_type="text/event-stream")

        return await chat_orchestrator.run(request_payload, session)
    except ProviderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"provider '{exc.provider_name}' not found",
        ) from exc
    except (httpx.HTTPError, TimeoutError, RuntimeError, OSError, ValueError) as exc:
        raise admin_test_chat_provider_exception(exc) from exc


@router.get("/providers/{provider_name}/models", response_model=list[ProviderModelRead])
async def list_provider_models(
    provider_name: str,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ProviderModelRead]:
    provider = await session.scalar(select(ProviderRecord).where(ProviderRecord.name == provider_name))
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="provider not found")
    rows = list(
        await session.scalars(
        select(ProviderModelRecord)
        .where(ProviderModelRecord.provider_id == provider.id)
        .order_by(ProviderModelRecord.native_model.asc())
        )
    )
    pricing_rows = list(
        await session.scalars(
            select(ModelPricingRecord)
            .where(ModelPricingRecord.provider_name == provider_name)
            .order_by(ModelPricingRecord.native_model.asc())
        )
    )
    pricing_by_model = {row.native_model: row for row in pricing_rows}
    return [
        ProviderModelRead(
            id=row.id,
            native_model=row.native_model,
            exposed_model_id=row.exposed_model_id,
            source=row.source,
            enabled=row.enabled,
            manually_overridden=row.manually_overridden,
            pricing=serialize_pricing(pricing_by_model.get(row.native_model)),
        )
        for row in rows
    ]


@router.post("/providers/{provider_name}/rediscover", response_model=list[ProviderModelRead])
async def rediscover_provider_models(
    provider_name: str,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ProviderModelRead]:
    provider = await session.scalar(select(ProviderRecord).where(ProviderRecord.name == provider_name))
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="provider not found")
    await pricing.sync_provider_pricing(session, provider.name)
    rows = await discovery.sync_provider_models(session, provider)
    pricing_rows = list(
        await session.scalars(select(ModelPricingRecord).where(ModelPricingRecord.provider_name == provider_name))
    )
    pricing_by_model = {row.native_model: row for row in pricing_rows}
    return [
        ProviderModelRead(
            id=row.id,
            native_model=row.native_model,
            exposed_model_id=row.exposed_model_id,
            source=row.source,
            enabled=row.enabled,
            manually_overridden=row.manually_overridden,
            pricing=serialize_pricing(pricing_by_model.get(row.native_model)),
        )
        for row in rows
    ]


@router.patch("/providers/{provider_name}/models/{native_model}", response_model=ProviderModelRead)
async def patch_provider_model(
    provider_name: str,
    native_model: str,
    payload: ProviderModelPatch,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ProviderModelRead:
    provider = await session.scalar(select(ProviderRecord).where(ProviderRecord.name == provider_name))
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="provider not found")
    row = await session.scalar(
        select(ProviderModelRecord).where(
            ProviderModelRecord.provider_id == provider.id,
            ProviderModelRecord.native_model == native_model,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="provider model not found")
    if payload.exposed_model_id is not None:
        row.exposed_model_id = payload.exposed_model_id
        row.manually_overridden = True
    if payload.enabled is not None:
        row.enabled = payload.enabled
        row.manually_overridden = True
    await session.commit()
    await session.refresh(row)
    pricing_row = await session.scalar(
        select(ModelPricingRecord).where(
            ModelPricingRecord.provider_name == provider_name,
            ModelPricingRecord.native_model == row.native_model,
        )
    )
    return ProviderModelRead(
        id=row.id,
        native_model=row.native_model,
        exposed_model_id=row.exposed_model_id,
        source=row.source,
        enabled=row.enabled,
        manually_overridden=row.manually_overridden,
        pricing=serialize_pricing(pricing_row),
    )


@router.post("/providers/{provider_name}/models", response_model=ProviderModelRead, status_code=status.HTTP_201_CREATED)
async def create_provider_model(
    provider_name: str,
    payload: ProviderModelCreate,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ProviderModelRead:
    provider = await session.scalar(select(ProviderRecord).where(ProviderRecord.name == provider_name))
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="provider not found")
    row = ProviderModelRecord(
        provider_id=provider.id,
        native_model=payload.native_model,
        exposed_model_id=payload.exposed_model_id,
        source="manual_override",
        enabled=payload.enabled,
        manually_overridden=True,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="provider model already exists") from exc
    await session.refresh(row)
    pricing_row = await session.scalar(
        select(ModelPricingRecord).where(
            ModelPricingRecord.provider_name == provider_name,
            ModelPricingRecord.native_model == row.native_model,
        )
    )
    return ProviderModelRead(
        id=row.id,
        native_model=row.native_model,
        exposed_model_id=row.exposed_model_id,
        source=row.source,
        enabled=row.enabled,
        manually_overridden=row.manually_overridden,
        pricing=serialize_pricing(pricing_row),
    )


@router.delete("/providers/{provider_name}/models/{native_model}", response_model=ProviderModelRead)
async def delete_provider_model(
    provider_name: str,
    native_model: str,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ProviderModelRead:
    provider = await session.scalar(select(ProviderRecord).where(ProviderRecord.name == provider_name))
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="provider not found")
    row = await session.scalar(
        select(ProviderModelRecord).where(
            ProviderModelRecord.provider_id == provider.id,
            ProviderModelRecord.native_model == native_model,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="provider model not found")
    pricing_row = await session.scalar(
        select(ModelPricingRecord).where(
            ModelPricingRecord.provider_name == provider_name,
            ModelPricingRecord.native_model == row.native_model,
        )
    )
    payload = ProviderModelRead(
        id=row.id,
        native_model=row.native_model,
        exposed_model_id=row.exposed_model_id,
        source=row.source,
        enabled=row.enabled,
        manually_overridden=row.manually_overridden,
        pricing=serialize_pricing(pricing_row),
    )
    await session.delete(row)
    await session.commit()
    return payload


def serialize_pricing(row: ModelPricingRecord | None) -> ModelPricingRead | None:
    if row is None:
        return None

    return ModelPricingRead(
        provider_name=row.provider_name,
        native_model=row.native_model,
        source_kind=row.source_kind,
        source_url=row.source_url,
        source_label=row.source_label,
        currency=row.currency,
        unit=row.unit,
        input_price=row.input_price,
        cached_input_price=row.cached_input_price,
        output_price=row.output_price,
        input_price_high=row.input_price_high,
        cached_input_price_high=row.cached_input_price_high,
        output_price_high=row.output_price_high,
        high_price_threshold_tokens=row.high_price_threshold_tokens,
        notes=row.notes,
        synced_at=row.synced_at.isoformat(),
    )


@router.post("/providers/{provider_name}/pricing/refresh", response_model=list[ProviderModelRead])
async def refresh_provider_pricing(
    provider_name: str,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ProviderModelRead]:
    provider = await session.scalar(select(ProviderRecord).where(ProviderRecord.name == provider_name))
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="provider not found")
    await pricing.sync_provider_pricing(session, provider_name)
    return await list_provider_models(provider_name, None, session)


@router.patch("/providers/{provider_name}/models/{native_model}/pricing", response_model=ModelPricingRead)
async def patch_provider_model_pricing(
    provider_name: str,
    native_model: str,
    payload: PricingOverridePatch,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ModelPricingRead:
    row = await session.scalar(
        select(ModelPricingRecord).where(
            ModelPricingRecord.provider_name == provider_name,
            ModelPricingRecord.native_model == native_model,
        )
    )
    if row is None:
        row = ModelPricingRecord(
            provider_name=provider_name,
            native_model=native_model,
            source_kind="manual_override",
            source_url="manual://admin",
            source_label="Manual Pricing Override",
            currency="USD",
            unit="1M tokens",
        )
        session.add(row)

    row.source_kind = "manual_override"
    row.source_url = "manual://admin"
    row.source_label = "Manual Pricing Override"
    row.input_price = payload.input_price
    row.cached_input_price = payload.cached_input_price
    row.output_price = payload.output_price
    row.input_price_high = payload.input_price_high
    row.cached_input_price_high = payload.cached_input_price_high
    row.output_price_high = payload.output_price_high
    row.high_price_threshold_tokens = payload.high_price_threshold_tokens
    row.notes = payload.notes
    row.synced_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(row)
    return serialize_pricing(row)  # type: ignore[return-value]
