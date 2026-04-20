from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, model_validator, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery.service import ProviderDiscoveryService
from app.core.db import get_session
from app.core.models import ProviderModelRecord, ProviderRecord
from app.core.settings import Settings

router = APIRouter(prefix="/admin", tags=["admin"])
settings = Settings()
discovery = ProviderDiscoveryService()


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


class ProviderModelRead(BaseModel):
    id: int
    native_model: str
    exposed_model_id: str
    source: str
    enabled: bool
    manually_overridden: bool


class ProviderModelPatch(BaseModel):
    exposed_model_id: str | None = None
    enabled: bool | None = None


class ProviderModelCreate(BaseModel):
    native_model: str
    exposed_model_id: str
    enabled: bool = True


def require_admin(x_admin_secret: str = Header(...)) -> None:
    if x_admin_secret != settings.admin_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid admin secret",
        )


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


@router.get("/providers/{provider_name}/models", response_model=list[ProviderModelRead])
async def list_provider_models(
    provider_name: str,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ProviderModelRead]:
    provider = await session.scalar(select(ProviderRecord).where(ProviderRecord.name == provider_name))
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="provider not found")
    rows = await session.scalars(
        select(ProviderModelRecord)
        .where(ProviderModelRecord.provider_id == provider.id)
        .order_by(ProviderModelRecord.native_model.asc())
    )
    return [ProviderModelRead.model_validate(row, from_attributes=True) for row in rows]


@router.post("/providers/{provider_name}/rediscover", response_model=list[ProviderModelRead])
async def rediscover_provider_models(
    provider_name: str,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ProviderModelRead]:
    provider = await session.scalar(select(ProviderRecord).where(ProviderRecord.name == provider_name))
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="provider not found")
    rows = await discovery.sync_provider_models(session, provider)
    return [ProviderModelRead.model_validate(row, from_attributes=True) for row in rows]


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
    return ProviderModelRead.model_validate(row, from_attributes=True)


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
    return ProviderModelRead.model_validate(row, from_attributes=True)
