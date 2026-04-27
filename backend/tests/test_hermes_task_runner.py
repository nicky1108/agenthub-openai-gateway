import pytest

from app.core.db import get_engine, get_session_factory
from app.core.models import AccountRecord, ApiKeyRecord, Base
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


@pytest.mark.asyncio
async def test_runner_completes_task_and_persists_events(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
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
