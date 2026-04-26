import pytest


@pytest.fixture(autouse=True)
def isolate_local_admin_email_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAILS_CSV", "")
