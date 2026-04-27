from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import AccountPlatformModelGrantRecord, AccountRecord

PLATFORM_MODEL_ACCESS_ALL = "all"
PLATFORM_MODEL_ACCESS_ALLOWLIST = "allowlist"
PLATFORM_MODEL_ACCESS_MODES = {PLATFORM_MODEL_ACCESS_ALL, PLATFORM_MODEL_ACCESS_ALLOWLIST}


def normalize_platform_model_access_mode(value: str | None) -> str:
    mode = (value or PLATFORM_MODEL_ACCESS_ALL).strip().lower()
    if mode not in PLATFORM_MODEL_ACCESS_MODES:
        return PLATFORM_MODEL_ACCESS_ALL
    return mode


def platform_model_id(model: dict[str, object]) -> str:
    return str(model["id"])


def platform_model_provider(model: dict[str, object]) -> str:
    return str(model.get("owned_by") or "platform")


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
) -> list[dict[str, object]]:
    if normalize_platform_model_access_mode(account.platform_model_access_mode) != PLATFORM_MODEL_ACCESS_ALLOWLIST:
        return platform_models
    allowed_model_ids = set(await account_allowed_platform_model_ids(session, account.id))
    return [model for model in platform_models if platform_model_id(model) in allowed_model_ids]


async def account_can_access_platform_model(
    session: AsyncSession,
    account: AccountRecord,
    model_id: str,
) -> bool:
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
    if account.platform_model_access_mode != PLATFORM_MODEL_ACCESS_ALLOWLIST:
        return

    unique_model_ids = list(dict.fromkeys(model_id.strip() for model_id in allowed_model_ids if model_id.strip()))
    session.add_all(
        [
            AccountPlatformModelGrantRecord(account_id=account.id, model_id=model_id)
            for model_id in unique_model_ids
        ]
    )
