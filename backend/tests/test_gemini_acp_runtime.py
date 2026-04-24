from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from app.adapters.base import ChatRequest
from app.orchestration.chat import ChatOrchestrator
from app.runtime.gemini_acp_client import GeminiAcpPromptResult
from app.runtime.provider_process_pool import provider_process_pool


class _FakeGeminiAcpClient:
    def __init__(self) -> None:
        self.initialize_calls = 0
        self.new_session_calls = 0
        self.set_model_calls = 0
        self.prompt_calls = 0
        self.active_prompts = 0
        self.max_active_prompts = 0
        self.healthy = True

    async def initialize(self) -> dict[str, object]:
        self.initialize_calls += 1
        return {"protocolVersion": 1}

    async def new_session(self, cwd: str) -> dict[str, object]:
        self.new_session_calls += 1
        return {"sessionId": "runtime-session"}

    async def set_model(self, session_id: str, model_id: str) -> dict[str, object]:
        self.set_model_calls += 1
        return {}

    async def prompt(self, session_id: str, text: str) -> GeminiAcpPromptResult:
        self.prompt_calls += 1
        self.active_prompts += 1
        self.max_active_prompts = max(self.max_active_prompts, self.active_prompts)
        try:
            await asyncio.sleep(0.05)
            return GeminiAcpPromptResult(
                result={"stopReason": "end_turn", "_meta": {"quota": {"token_count": {"input_tokens": 10, "output_tokens": 1}}}},
                updates=[
                    {
                        "sessionId": session_id,
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": "OK"},
                        },
                    }
                ],
            )
        finally:
            self.active_prompts -= 1

    def is_healthy(self) -> bool:
        return self.healthy


def _runtime_with_clients(*clients: _FakeGeminiAcpClient) -> dict[str, object]:
    return {
        "slots": [
            {
                "client": client,
                "lock": asyncio.Lock(),
                "initialized": False,
                "session_id": None,
                "model_id": None,
                "waiters": 0,
            }
            for client in clients
        ],
        "selection_lock": asyncio.Lock(),
        "next_slot": 0,
    }


def test_gemini_acp_runtime_uses_configured_pool_size(monkeypatch) -> None:
    provider_process_pool.clear()
    monkeypatch.setenv("GEMINI_ACP_POOL_SIZE", "3")
    orchestrator = ChatOrchestrator()
    provider = SimpleNamespace(
        name="gemini",
        cli_command="/opt/homebrew/bin/gemini",
        cli_args_json="[]",
        cli_env_json="{}",
        cli_cwd="/tmp",
    )
    try:
        runtime = orchestrator._gemini_acp_runtime(provider)
        slots = runtime["slots"]
        assert isinstance(slots, list)
        assert len(slots) == 3
        assert orchestrator._gemini_acp_key(provider).endswith(":pool=3")
    finally:
        provider_process_pool.clear()


@pytest.mark.asyncio
async def test_gemini_acp_runtime_serializes_prompts_and_logs_reuse(caplog) -> None:
    orchestrator = ChatOrchestrator()
    fake_client = _FakeGeminiAcpClient()
    runtime = _runtime_with_clients(fake_client)
    provider = SimpleNamespace(
        name="gemini",
        cli_command="/opt/homebrew/bin/gemini",
        cli_args_json="[]",
        cli_env_json="{}",
        cli_cwd="/tmp",
    )
    request_one = ChatRequest(
        provider_name="gemini",
        provider_model="gemini-2.5-flash",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
        request_id="req-one",
    )
    request_two = ChatRequest(
        provider_name="gemini",
        provider_model="gemini-2.5-flash",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
        request_id="req-two",
    )
    caplog.set_level(logging.INFO, logger="agenthub.gateway")

    orchestrator._gemini_acp_runtime = lambda _provider: runtime  # type: ignore[method-assign]

    result_one, result_two = await asyncio.gather(
        orchestrator._gemini_acp_chat(request_one, provider),
        orchestrator._gemini_acp_chat(request_two, provider),
    )

    assert result_one["choices"][0]["message"]["content"] == "OK"
    assert result_two["choices"][0]["message"]["content"] == "OK"
    assert fake_client.initialize_calls == 1
    assert fake_client.new_session_calls == 1
    assert fake_client.set_model_calls == 1
    assert fake_client.prompt_calls == 2
    assert fake_client.max_active_prompts == 1
    assert "gateway.gemini_acp.queue_wait" in caplog.text
    assert "gateway.gemini_acp.session_new" in caplog.text
    assert "gateway.gemini_acp.session_reuse" in caplog.text


@pytest.mark.asyncio
async def test_gemini_acp_runtime_distributes_concurrent_prompts_across_warm_pool() -> None:
    orchestrator = ChatOrchestrator()
    client_one = _FakeGeminiAcpClient()
    client_two = _FakeGeminiAcpClient()
    runtime = _runtime_with_clients(client_one, client_two)
    for index, slot in enumerate(runtime["slots"]):
        slot["initialized"] = True
        slot["session_id"] = f"warm-session-{index}"
        slot["model_id"] = "gemini-2.5-flash"
    provider = SimpleNamespace(
        name="gemini",
        cli_command="/opt/homebrew/bin/gemini",
        cli_args_json="[]",
        cli_env_json="{}",
        cli_cwd="/tmp",
    )
    requests = [
        ChatRequest(
            provider_name="gemini",
            provider_model="gemini-2.5-flash",
            messages=[{"role": "user", "content": "hello"}],
            stream=False,
            request_id=f"req-{index}",
        )
        for index in range(2)
    ]

    orchestrator._gemini_acp_runtime = lambda _provider: runtime  # type: ignore[method-assign]

    await asyncio.gather(*(orchestrator._gemini_acp_chat(request, provider) for request in requests))

    assert client_one.prompt_calls == 1
    assert client_two.prompt_calls == 1


@pytest.mark.asyncio
async def test_gemini_acp_runtime_reuses_warm_idle_slot_before_cold_slot(monkeypatch) -> None:
    orchestrator = ChatOrchestrator()
    monkeypatch.setattr(orchestrator, "_schedule_gemini_acp_pool_warmup", lambda *args: None, raising=False)
    warm_client = _FakeGeminiAcpClient()
    cold_client = _FakeGeminiAcpClient()
    runtime = _runtime_with_clients(warm_client, cold_client)
    provider = SimpleNamespace(
        name="gemini",
        cli_command="/opt/homebrew/bin/gemini",
        cli_args_json="[]",
        cli_env_json="{}",
        cli_cwd="/tmp",
    )
    request = ChatRequest(
        provider_name="gemini",
        provider_model="gemini-2.5-flash",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
        request_id="req-warm",
    )

    orchestrator._gemini_acp_runtime = lambda _provider: runtime  # type: ignore[method-assign]

    await orchestrator._gemini_acp_chat(request, provider)
    await orchestrator._gemini_acp_chat(request, provider)

    assert warm_client.prompt_calls == 2
    assert warm_client.initialize_calls == 1
    assert cold_client.prompt_calls == 0
    assert cold_client.initialize_calls == 0


@pytest.mark.asyncio
async def test_gemini_acp_runtime_prewarms_cold_idle_slots_after_prompt(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_ACP_PREWARM_ENABLED", "true")
    orchestrator = ChatOrchestrator()
    warm_client = _FakeGeminiAcpClient()
    cold_client = _FakeGeminiAcpClient()
    runtime = _runtime_with_clients(warm_client, cold_client)
    provider = SimpleNamespace(
        name="gemini",
        cli_command="/opt/homebrew/bin/gemini",
        cli_args_json="[]",
        cli_env_json="{}",
        cli_cwd="/tmp",
    )
    request = ChatRequest(
        provider_name="gemini",
        provider_model="gemini-2.5-flash",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
        request_id="req-prewarm",
    )

    orchestrator._gemini_acp_runtime = lambda _provider: runtime  # type: ignore[method-assign]

    await orchestrator._gemini_acp_chat(request, provider)
    for _ in range(10):
        task = runtime.get("warmup_task")
        if isinstance(task, asyncio.Task):
            await task
            break
        if cold_client.initialize_calls:
            break
        await asyncio.sleep(0)

    assert warm_client.prompt_calls == 1
    assert cold_client.prompt_calls == 0
    assert cold_client.initialize_calls == 1
    assert cold_client.new_session_calls == 1
    assert cold_client.set_model_calls == 1


@pytest.mark.asyncio
async def test_gemini_acp_runtime_waits_for_warm_busy_slot_before_cold_slot(monkeypatch) -> None:
    orchestrator = ChatOrchestrator()
    monkeypatch.setattr(orchestrator, "_schedule_gemini_acp_pool_warmup", lambda *args: None, raising=False)
    warm_client = _FakeGeminiAcpClient()
    cold_client = _FakeGeminiAcpClient()
    runtime = _runtime_with_clients(warm_client, cold_client)
    provider = SimpleNamespace(
        name="gemini",
        cli_command="/opt/homebrew/bin/gemini",
        cli_args_json="[]",
        cli_env_json="{}",
        cli_cwd="/tmp",
    )
    request = ChatRequest(
        provider_name="gemini",
        provider_model="gemini-2.5-flash",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
        request_id="req-warm-busy",
    )

    orchestrator._gemini_acp_runtime = lambda _provider: runtime  # type: ignore[method-assign]

    await orchestrator._gemini_acp_chat(request, provider)
    await asyncio.gather(
        orchestrator._gemini_acp_chat(request, provider),
        orchestrator._gemini_acp_chat(request, provider),
    )

    assert warm_client.prompt_calls == 3
    assert cold_client.prompt_calls == 0


@pytest.mark.asyncio
async def test_gemini_acp_runtime_resets_stale_session_when_client_is_unhealthy(caplog) -> None:
    orchestrator = ChatOrchestrator()
    fake_client = _FakeGeminiAcpClient()
    fake_client.healthy = False
    runtime = _runtime_with_clients(fake_client)
    slot = runtime["slots"][0]
    slot["initialized"] = True
    slot["session_id"] = "stale-session"
    slot["model_id"] = "gemini-2.5-flash"
    provider = SimpleNamespace(
        name="gemini",
        cli_command="/opt/homebrew/bin/gemini",
        cli_args_json="[]",
        cli_env_json="{}",
        cli_cwd="/tmp",
    )
    request = ChatRequest(
        provider_name="gemini",
        provider_model="gemini-2.5-flash",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
        request_id="req-reset",
    )
    caplog.set_level(logging.INFO, logger="agenthub.gateway")

    orchestrator._gemini_acp_runtime = lambda _provider: runtime  # type: ignore[method-assign]

    result = await orchestrator._gemini_acp_chat(request, provider)

    assert result["choices"][0]["message"]["content"] == "OK"
    assert fake_client.initialize_calls == 1
    assert fake_client.new_session_calls == 1
    assert fake_client.set_model_calls == 1
    assert slot["session_id"] == "runtime-session"
    assert "gateway.gemini_acp.session_reset" in caplog.text


@pytest.mark.asyncio
async def test_gemini_acp_runtime_can_prewarm_session_without_prompt(monkeypatch, caplog) -> None:
    monkeypatch.setenv("GEMINI_ACP_ENABLED", "true")
    orchestrator = ChatOrchestrator()
    fake_client = _FakeGeminiAcpClient()
    runtime = _runtime_with_clients(fake_client)
    provider = SimpleNamespace(
        name="gemini",
        cli_enabled=True,
        cli_command="/opt/homebrew/bin/gemini",
        cli_args_json="[]",
        cli_env_json="{}",
        cli_cwd="/tmp",
    )
    caplog.set_level(logging.INFO, logger="agenthub.gateway")

    orchestrator._gemini_acp_runtime = lambda _provider: runtime  # type: ignore[method-assign]

    await orchestrator.prewarm_provider(provider)

    slot = runtime["slots"][0]
    assert slot["initialized"] is True
    assert slot["session_id"] == "runtime-session"
    assert slot["model_id"] is None
    assert fake_client.initialize_calls == 1
    assert fake_client.new_session_calls == 1
    assert fake_client.set_model_calls == 0
    assert fake_client.prompt_calls == 0
    assert "gateway.gemini_acp.startup_prewarm" in caplog.text
