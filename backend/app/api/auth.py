import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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


def serialize_account(account: AccountRecord) -> dict[str, object]:
    return {"id": account.id, "name": account.name, "email": account.email}


def normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterPayload,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    existing_email = await session.scalar(select(AccountRecord).where(AccountRecord.email == payload.email))
    if existing_email is not None:
        raise HTTPException(status_code=409, detail="email already exists")
    existing_name = await session.scalar(select(AccountRecord).where(AccountRecord.name == payload.name))
    if existing_name is not None:
        raise HTTPException(status_code=409, detail="account name already exists")

    account = AccountRecord(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    session.add(account)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="account already exists") from exc
    await session.refresh(account)
    return serialize_account(account)


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

    raw_token = secrets.token_urlsafe(32)
    session_record = AuthSessionRecord(
        account_id=account.id,
        session_token_hash=hash_api_key(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(session_record)
    await session.commit()

    response.set_cookie("agh_session", raw_token, httponly=True, samesite="lax")
    return serialize_account(account)


@router.get("/oauth/github")
async def github_oauth_entry() -> RedirectResponse:
    return RedirectResponse(url="/auth/oauth/github/callback-placeholder", status_code=302)


@router.get("/oauth/google")
async def google_oauth_entry() -> RedirectResponse:
    return RedirectResponse(url="/auth/oauth/google/callback-placeholder", status_code=302)


@router.get("/me")
async def me(
    agh_session: str | None = Cookie(default=None, alias="agh_session"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    if not agh_session:
        raise HTTPException(status_code=401, detail="missing session cookie")

    session_record = await session.scalar(
        select(AuthSessionRecord).where(AuthSessionRecord.session_token_hash == hash_api_key(agh_session))
    )
    if session_record is None or session_record.status != "active":
        raise HTTPException(status_code=401, detail="invalid session")

    if normalize_timestamp(session_record.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="session expired")

    account = await session.scalar(select(AccountRecord).where(AccountRecord.id == session_record.account_id))
    if account is None or account.status != "active":
        raise HTTPException(status_code=401, detail="account is not active")

    return serialize_account(account)
