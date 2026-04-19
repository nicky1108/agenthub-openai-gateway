from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.models import ProviderRecord
from app.core.settings import Settings

router = APIRouter(prefix="/admin", tags=["admin"])
settings = Settings()


class ProviderCreate(BaseModel):
    name: str
    http_enabled: bool
    cli_enabled: bool
    route_policy: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if ":" in value:
            raise ValueError("must not contain ':'")
        return value


class ProviderRead(ProviderCreate):
    id: int


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
    return ProviderRead.model_validate(record, from_attributes=True)


@router.get("/providers", response_model=list[ProviderRead])
async def list_providers(
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ProviderRead]:
    rows = await session.scalars(select(ProviderRecord).order_by(ProviderRecord.id.asc()))
    return [ProviderRead.model_validate(row, from_attributes=True) for row in rows]
