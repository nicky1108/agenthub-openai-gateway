from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, model_validator, field_validator
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import generate_api_key, hash_api_key
from app.discovery.service import ProviderDiscoveryService
from app.core.db import get_session
from app.core.models import AccountRecord, ApiKeyRecord, ModelPricingRecord, ProviderModelRecord, ProviderRecord, UsageRecord
from app.pricing.service import OfficialPricingService
from app.core.settings import Settings

router = APIRouter(prefix="/admin", tags=["admin"])
discovery = ProviderDiscoveryService()
pricing = OfficialPricingService()


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
    http_headers_json: str = "{}"
    cli_command: str | None = None
    cli_args_json: str = "[]"
    cli_env_json: str = "{}"
    cli_cwd: str | None = None


class ProviderHealth(BaseModel):
    name: str
    route_policy: str
    capabilities: dict[str, bool]


class ModelPricingRead(BaseModel):
    provider_name: str
    native_model: str
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


class AccountCreate(BaseModel):
    name: str
    notes: str | None = None


class AccountRead(BaseModel):
    id: int
    name: str
    status: str
    notes: str | None = None


class ApiKeyCreate(BaseModel):
    account_id: int
    name: str
    per_minute: int | None = None
    per_hour: int | None = None
    per_day: int | None = None


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


def get_settings() -> Settings:
    return Settings()


def require_admin(
    x_admin_secret: str = Header(...),
    settings: Settings = Depends(get_settings),
) -> None:
    if x_admin_secret != settings.admin_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid admin secret",
        )


def normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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
) -> ProviderRead:
    record = ProviderRecord(**payload.model_dump())
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
    return ProviderRead.model_validate(record, from_attributes=True)


@router.get("/providers", response_model=list[ProviderRead])
async def list_providers(
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ProviderRead]:
    rows = await session.scalars(select(ProviderRecord).order_by(ProviderRecord.id.asc()))
    return [ProviderRead.model_validate(row, from_attributes=True) for row in rows]


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
) -> AccountRead:
    account = AccountRecord(name=payload.name, notes=payload.notes)
    session.add(account)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="account already exists") from exc
    await session.refresh(account)
    return AccountRead.model_validate(account, from_attributes=True)


@router.get("/accounts", response_model=list[AccountRead])
async def list_accounts(
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AccountRead]:
    rows = await session.scalars(select(AccountRecord).order_by(AccountRecord.id.asc()))
    return [AccountRead.model_validate(row, from_attributes=True) for row in rows]


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
    rows = await session.scalars(select(ApiKeyRecord).order_by(ApiKeyRecord.id.asc()))
    return [
        ApiKeyRead(
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
        for row in rows
    ]


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
    await session.commit()
    await session.refresh(row)
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


def serialize_pricing(row: ModelPricingRecord | None) -> ModelPricingRead | None:
    if row is None:
        return None

    return ModelPricingRead(
        provider_name=row.provider_name,
        native_model=row.native_model,
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
