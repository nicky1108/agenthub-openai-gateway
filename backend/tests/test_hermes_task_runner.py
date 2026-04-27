import pytest
from sqlalchemy import select

from app.core.db import get_engine, get_session_factory
from app.core.models import (
    AccountRecord,
    ApiKeyRecord,
    Base,
    CreditLedgerRecord,
    ModelPricingRecord,
    UsageRecord,
)
from app.services.hermes_client import HermesResponseEvent
from app.services.hermes_tasks import (
    HERMES_STATUS_COMPLETED,
    HermesTaskCreate,
    create_hermes_task,
    get_hermes_task_for_account,
    list_hermes_task_events,
)
from app.runtime.hermes_task_runner import HermesTaskRunner


class FakeHermesClient:
    async def stream_response(self, request):
        yield HermesResponseEvent(type="response.output_text.delta", payload={"delta": "hello"})
        yield HermesResponseEvent(type="response.output_text.delta", payload={"delta": " world"})
        yield HermesResponseEvent(
            type="response.completed",
            payload={"response": {"id": "resp-1", "output_text": "hello world"}},
        )


def _add_hermes_pricing(session) -> None:
    session.add(
        ModelPricingRecord(
            provider_name="hermes",
            native_model="hermes-agent",
            source_kind="manual",
            source_url="local",
            source_label="Hermes",
            input_price=10.0,
            output_price=20.0,
        )
    )


@pytest.mark.asyncio
async def test_runner_completes_task_and_persists_events(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("HERMES_MODEL", "hermes-agent")
    engine = get_engine(database_url)
    session_factory = get_session_factory(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        account = AccountRecord(name="acct", credit_balance=100)
        session.add(account)
        await session.flush()
        api_key = ApiKeyRecord(account_id=account.id, name="key", key_prefix="sk-test", secret_hash="hash")
        session.add(api_key)
        _add_hermes_pricing(session)
        await session.commit()
        task = await create_hermes_task(
            session,
            account=account,
            api_key=api_key,
            payload=HermesTaskCreate(input_text="hello"),
        )
        await session.commit()

    runner = HermesTaskRunner(
        sessionmaker=session_factory,
        client_factory=lambda: FakeHermesClient(),
        max_concurrent_tasks=1,
        task_max_runtime_seconds=60,
    )
    await runner.run_task_once(task.id)

    async with session_factory() as session:
        loaded = await get_hermes_task_for_account(session, task.id, account.id)
        events = await list_hermes_task_events(session, task.id, after_seq=0)

    await engine.dispose()

    assert loaded is not None
    assert loaded.status == HERMES_STATUS_COMPLETED
    assert loaded.output_text == "hello world"
    assert loaded.response_id == "resp-1"
    assert [event.event_type for event in events] == [
        "task.status",
        "response.output_text.delta",
        "response.output_text.delta",
        "response.completed",
        "task.status",
    ]


@pytest.mark.asyncio
async def test_runner_settles_successful_task_usage(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("HERMES_MODEL", "hermes-agent")
    engine = get_engine(database_url)
    session_factory = get_session_factory(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        account = AccountRecord(name="billing-acct", credit_balance=100)
        session.add(account)
        await session.flush()
        api_key = ApiKeyRecord(account_id=account.id, name="key", key_prefix="sk-bill", secret_hash="hash")
        session.add(api_key)
        _add_hermes_pricing(session)
        await session.commit()
        task = await create_hermes_task(
            session,
            account=account,
            api_key=api_key,
            payload=HermesTaskCreate(input_text="hello"),
        )
        await session.commit()

    runner = HermesTaskRunner(
        sessionmaker=session_factory,
        client_factory=lambda: FakeHermesClient(),
        max_concurrent_tasks=1,
        task_max_runtime_seconds=60,
    )
    await runner.run_task_once(task.id)

    async with session_factory() as session:
        usage_rows = list(await session.scalars(select(UsageRecord)))
        ledger_rows = list(await session.scalars(select(CreditLedgerRecord)))
        account_row = await session.get(AccountRecord, account.id)

    await engine.dispose()

    assert len(usage_rows) == 1
    assert usage_rows[0].provider_name == "hermes"
    assert usage_rows[0].model_id == "hermes:hermes-agent"
    assert usage_rows[0].outcome == "success"
    assert usage_rows[0].input_tokens is not None and usage_rows[0].input_tokens > 0
    assert usage_rows[0].output_tokens is not None and usage_rows[0].output_tokens > 0
    assert len(ledger_rows) == 1
    assert ledger_rows[0].provider_name == "hermes"
    assert ledger_rows[0].credits_delta < 0
    assert account_row is not None
    assert account_row.credit_balance < 100
