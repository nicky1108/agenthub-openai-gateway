from app.core.models import AccountRecord
from app.core.settings import Settings


def account_is_named_admin(account: AccountRecord | None, settings: Settings) -> bool:
    if account is None or account.status != "active":
        return False
    if bool(getattr(account, "is_admin", False)):
        return True
    if not account.email:
        return False
    return account.email.lower() in settings.admin_emails
