from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password, verify_password
from app.auth.service import hash_api_key
from app.core.db import get_session
from app.core.models import AccountRecord, AuthSessionRecord

router = APIRouter(prefix="/auth", tags=["auth"])


def validate_email_address(value: str) -> str:
    email = value.strip()
    if " " in email or email.count("@") != 1:
        raise ValueError("invalid email address")

    local_part, domain = email.split("@", 1)
    if not local_part or not domain or "." not in domain:
        raise ValueError("invalid email address")
    if domain.startswith(".") or domain.endswith(".") or ".." in domain:
        raise ValueError("invalid email address")

    return email


class RegisterPayload(BaseModel):
    name: str
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return validate_email_address(value)


class LoginPayload(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return validate_email_address(value)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterPayload,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    existing = await session.scalar(select(AccountRecord).where(AccountRecord.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="email already exists")

    account = AccountRecord(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return {"id": account.id, "name": account.name, "email": account.email}


@router.post("/login")
async def login(
    payload: LoginPayload,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    account = await session.scalar(select(AccountRecord).where(AccountRecord.email == payload.email))
    if account is None or not account.password_hash or not verify_password(
        payload.password, account.password_hash
    ):
        raise HTTPException(status_code=401, detail="invalid credentials")

    raw_token = f"agh_{account.id}_{datetime.now(timezone.utc).timestamp()}"
    session_record = AuthSessionRecord(
        account_id=account.id,
        session_token_hash=hash_api_key(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(session_record)
    await session.commit()

    response.set_cookie("agh_session", raw_token, httponly=True, samesite="lax")
    return {"id": account.id, "name": account.name, "email": account.email}
