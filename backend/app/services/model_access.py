from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.admins import account_is_named_admin
from app.core.models import AccountPlatformModelGrantRecord, AccountRecord
from app.core.settings import Settings

PLATFORM_MODEL_ACCESS_ALL = "all"
PLATFORM_MODEL_ACCESS_ALLOWLIST = "allowlist"
PLATFORM_MODEL_ACCESS_MODES = {PLATFORM_MODEL_ACCESS_ALL, PLATFORM_MODEL_ACCESS_ALLOWLIST}
ADMIN_GRANT_REQUIRED_MODEL_PREFIXES = ("hermes:",)


def normalize_platform_model_access_mode(value: str | None) -> str:
    mode = (value or PLATFORM_MODEL_ACCESS_ALL).strip().lower()
    if mode not in PLATFORM_MODEL_ACCESS_MODES:
        return PLATFORM_MODEL_ACCESS_ALL
    return mode


def platform_model_id(model: dict[str, object]) -> str:
    return str(model["id"])


def platform_model_provider(model: dict[str, object]) -> str:
    return str(model.get("owned_by") or "platform")


def platform_model_requires_admin_grant(model_id: str) -> bool:
    return model_id.startswith(ADMIN_GRANT_REQUIRED_MODEL_PREFIXES)


def account_has_admin_permission(account: AccountRecord, settings: Settings | None = None) -> bool:
    return account_is_named_admin(account, settings or Settings())


async def account_allowed_platform_model_ids(session: AsyncSession, account_id: int) -> list[str]:
    rows = list(
        await session.scalars(
            select(AccountPlatformModelGrantRecord.model_id)
            .where(AccountPlatformModelGrantRecord.account_id == account_id)
            .order_by(AccountPlatformModelGrantRecord.model_id.asc())
        )
    )
    return rows


async def filter_platform_models_for_account(
    session: AsyncSession,
    account: AccountRecord,
    platform_models: list[dict[str, object]],
    settings: Settings | None = None,
) -> list[dict[str, object]]:
    access_mode = normalize_platform_model_access_mode(account.platform_model_access_mode)
    has_admin_restricted_models = any(
        platform_model_requires_admin_grant(platform_model_id(model)) for model in platform_models
    )
    if access_mode != PLATFORM_MODEL_ACCESS_ALLOWLIST and not has_admin_restricted_models:
        return platform_models

    allowed_model_ids = set(await account_allowed_platform_model_ids(session, account.id))
    has_admin_permission = (
        account_has_admin_permission(account, settings) if has_admin_restricted_models else False
    )
    visible_models: list[dict[str, object]] = []
    for model in platform_models:
        model_id = platform_model_id(model)
        if platform_model_requires_admin_grant(model_id):
            if has_admin_permission and model_id in allowed_model_ids:
                visible_models.append(model)
            continue
        if access_mode != PLATFORM_MODEL_ACCESS_ALLOWLIST or model_id in allowed_model_ids:
            visible_models.append(model)
    return visible_models


async def account_can_access_platform_model(
    session: AsyncSession,
    account: AccountRecord,
    model_id: str,
    settings: Settings | None = None,
) -> bool:
    if platform_model_requires_admin_grant(model_id):
        allowed_model_ids = set(await account_allowed_platform_model_ids(session, account.id))
        return account_has_admin_permission(account, settings) and model_id in allowed_model_ids
    if normalize_platform_model_access_mode(account.platform_model_access_mode) != PLATFORM_MODEL_ACCESS_ALLOWLIST:
        return True
    allowed_model_ids = set(await account_allowed_platform_model_ids(session, account.id))
    return model_id in allowed_model_ids


async def replace_account_platform_model_access(
    session: AsyncSession,
    account: AccountRecord,
    mode: str,
    allowed_model_ids: list[str],
) -> None:
    account.platform_model_access_mode = normalize_platform_model_access_mode(mode)
    await session.execute(
        delete(AccountPlatformModelGrantRecord).where(AccountPlatformModelGrantRecord.account_id == account.id)
    )
    unique_model_ids = list(dict.fromkeys(model_id.strip() for model_id in allowed_model_ids if model_id.strip()))
    if account.platform_model_access_mode != PLATFORM_MODEL_ACCESS_ALLOWLIST:
        unique_model_ids = [
            model_id for model_id in unique_model_ids if platform_model_requires_admin_grant(model_id)
        ]
    if not unique_model_ids:
        return

    session.add_all(
        [
            AccountPlatformModelGrantRecord(account_id=account.id, model_id=model_id)
            for model_id in unique_model_ids
        ]
    )
