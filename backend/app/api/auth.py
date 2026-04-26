import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.admins import account_is_named_admin
from app.auth.passwords import hash_password, verify_password
from app.auth.service import hash_api_key
from app.core.db import get_session
from app.core.models import AccountRecord, AuthSessionRecord
from app.core.settings import Settings

router = APIRouter(prefix="/auth", tags=["auth"])
SESSION_COOKIE_NAME = "agh_session"
OAUTH_STATE_COOKIE_NAME = "agh_oauth_state"
OAUTH_PROVIDER_COOKIE_NAME = "agh_oauth_provider"


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


class AuthProviderStatus(BaseModel):
    email_password_enabled: bool
    github_enabled: bool
    google_enabled: bool


def serialize_account(account: AccountRecord, settings: Settings) -> dict[str, object]:
    return {
        "id": account.id,
        "name": account.name,
        "email": account.email,
        "is_admin": account_is_named_admin(account, settings),
    }


def normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def get_settings() -> Settings:
    return Settings()


async def create_auth_session(response: Response, session: AsyncSession, account: AccountRecord) -> None:
    raw_token = secrets.token_urlsafe(32)
    session_record = AuthSessionRecord(
        account_id=account.id,
        session_token_hash=hash_api_key(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(session_record)
    await session.commit()
    response.set_cookie(SESSION_COOKIE_NAME, raw_token, httponly=True, samesite="lax")


def normalize_frontend_redirect(frontend_base_url: str) -> str:
    return frontend_base_url.rstrip("/") + "/"


def build_oauth_redirect_response(url: str, provider: str, state: str) -> RedirectResponse:
    response = RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(OAUTH_STATE_COOKIE_NAME, state, httponly=True, samesite="lax", max_age=600)
    response.set_cookie(OAUTH_PROVIDER_COOKIE_NAME, provider, httponly=True, samesite="lax", max_age=600)
    return response


def require_oauth_provider_enabled(provider: str, settings: Settings) -> None:
    enabled = settings.github_oauth_enabled if provider == "github" else settings.google_oauth_enabled
    if not enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"{provider} oauth is not configured")


async def exchange_github_code(code: str, redirect_uri: str) -> dict[str, str]:
    settings = Settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_oauth_client_id,
                "client_secret": settings.github_oauth_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        response.raise_for_status()
        return response.json()


async def fetch_github_profile(access_token: str) -> dict[str, str]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        user_response = await client.get(
            "https://api.github.com/user",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {access_token}",
            },
        )
        user_response.raise_for_status()
        user_payload = user_response.json()
        email = user_payload.get("email")
        if not email:
            emails_response = await client.get(
                "https://api.github.com/user/emails",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                },
            )
            emails_response.raise_for_status()
            email_rows = emails_response.json()
            primary = next((row for row in email_rows if row.get("primary")), None)
            email = primary.get("email") if primary else (email_rows[0].get("email") if email_rows else None)
        return {
            "subject": str(user_payload["id"]),
            "email": email or "",
            "name": user_payload.get("name") or user_payload.get("login") or "github-user",
        }


async def exchange_google_code(code: str, redirect_uri: str) -> dict[str, str]:
    settings = Settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
        response.raise_for_status()
        return response.json()


async def fetch_google_profile(access_token: str) -> dict[str, str]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        payload = response.json()
        return {
            "subject": payload["sub"],
            "email": payload.get("email", ""),
            "name": payload.get("name") or payload.get("email") or "google-user",
        }


async def upsert_oauth_account(
    session: AsyncSession,
    provider: str,
    subject: str,
    email: str | None,
    name: str,
) -> AccountRecord:
    account = await session.scalar(
        select(AccountRecord).where(
            AccountRecord.oauth_provider == provider,
            AccountRecord.oauth_subject == subject,
        )
    )
    if account is None and email:
        account = await session.scalar(select(AccountRecord).where(AccountRecord.email == email))

    if account is None:
        account = AccountRecord(
            name=name,
            email=email,
            oauth_provider=provider,
            oauth_subject=subject,
        )
        session.add(account)
        await session.flush()
        return account

    if account.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="account is not active")

    account.name = name
    if email:
        account.email = email
    if account.oauth_provider not in (None, provider):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="oauth account is already linked")
    if account.oauth_subject not in (None, subject):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="oauth subject does not match account")

    account.oauth_provider = provider
    account.oauth_subject = subject
    await session.flush()
    return account


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterPayload,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
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
    await create_auth_session(response, session, account)
    return serialize_account(account, settings)


@router.post("/login")
async def login(
    payload: LoginPayload,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    account = await session.scalar(select(AccountRecord).where(AccountRecord.email == payload.email))
    if account is None or not account.password_hash or not verify_password(
        payload.password, account.password_hash
    ):
        raise HTTPException(status_code=401, detail="invalid credentials")

    await create_auth_session(response, session, account)
    return serialize_account(account, settings)


@router.post("/logout")
async def logout(
    response: Response,
    agh_session: str | None = Cookie(default=None, alias="agh_session"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    if agh_session:
        session_record = await session.scalar(
            select(AuthSessionRecord).where(AuthSessionRecord.session_token_hash == hash_api_key(agh_session))
        )
        if session_record is not None:
            session_record.status = "revoked"
            await session.commit()
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"status": "logged_out"}


@router.get("/providers", response_model=AuthProviderStatus)
async def auth_provider_status(settings: Settings = Depends(get_settings)) -> AuthProviderStatus:
    return AuthProviderStatus(
        email_password_enabled=True,
        github_enabled=settings.github_oauth_enabled,
        google_enabled=settings.google_oauth_enabled,
    )


@router.get("/oauth/github")
async def github_oauth_entry(request: Request, settings: Settings = Depends(get_settings)) -> RedirectResponse:
    require_oauth_provider_enabled("github", settings)
    state = secrets.token_urlsafe(24)
    authorize_url = "https://github.com/login/oauth/authorize?" + urlencode(
        {
            "client_id": settings.github_oauth_client_id,
            "redirect_uri": str(request.url_for("github_oauth_callback")),
            "scope": "read:user user:email",
            "state": state,
        }
    )
    return build_oauth_redirect_response(authorize_url, "github", state)


@router.get("/oauth/google")
async def google_oauth_entry(request: Request, settings: Settings = Depends(get_settings)) -> RedirectResponse:
    require_oauth_provider_enabled("google", settings)
    state = secrets.token_urlsafe(24)
    authorize_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": str(request.url_for("google_oauth_callback")),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    return build_oauth_redirect_response(authorize_url, "google", state)


async def finalize_oauth_login(
    *,
    session: AsyncSession,
    response: Response,
    provider: str,
    subject: str,
    email: str | None,
    name: str,
) -> Response:
    account = await upsert_oauth_account(session, provider=provider, subject=subject, email=email, name=name)
    await create_auth_session(response, session, account)
    response.delete_cookie(OAUTH_STATE_COOKIE_NAME)
    response.delete_cookie(OAUTH_PROVIDER_COOKIE_NAME)
    return response


def validate_oauth_callback(provider: str, code: str | None, state: str | None, cookie_state: str | None, cookie_provider: str | None) -> None:
    if not code or not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing oauth callback parameters")
    if cookie_state != state or cookie_provider != provider:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid oauth state")


@router.get("/oauth/github/callback", name="github_oauth_callback")
async def github_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    agh_oauth_state: str | None = Cookie(default=None, alias=OAUTH_STATE_COOKIE_NAME),
    agh_oauth_provider: str | None = Cookie(default=None, alias=OAUTH_PROVIDER_COOKIE_NAME),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    require_oauth_provider_enabled("github", settings)
    validate_oauth_callback("github", code, state, agh_oauth_state, agh_oauth_provider)
    token_payload = await exchange_github_code(code or "", str(request.url_for("github_oauth_callback")))
    profile = await fetch_github_profile(token_payload["access_token"])
    response = RedirectResponse(url=normalize_frontend_redirect(settings.frontend_base_url), status_code=status.HTTP_302_FOUND)
    return await finalize_oauth_login(
        session=session,
        response=response,
        provider="github",
        subject=profile["subject"],
        email=profile.get("email"),
        name=profile["name"],
    )


@router.get("/oauth/google/callback", name="google_oauth_callback")
async def google_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    agh_oauth_state: str | None = Cookie(default=None, alias=OAUTH_STATE_COOKIE_NAME),
    agh_oauth_provider: str | None = Cookie(default=None, alias=OAUTH_PROVIDER_COOKIE_NAME),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    require_oauth_provider_enabled("google", settings)
    validate_oauth_callback("google", code, state, agh_oauth_state, agh_oauth_provider)
    token_payload = await exchange_google_code(code or "", str(request.url_for("google_oauth_callback")))
    profile = await fetch_google_profile(token_payload["access_token"])
    response = RedirectResponse(url=normalize_frontend_redirect(settings.frontend_base_url), status_code=status.HTTP_302_FOUND)
    return await finalize_oauth_login(
        session=session,
        response=response,
        provider="google",
        subject=profile["subject"],
        email=profile.get("email"),
        name=profile["name"],
    )


@router.get("/me")
async def me(
    agh_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
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

    return serialize_account(account, settings)
