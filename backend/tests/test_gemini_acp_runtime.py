from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from app.adapters.base import ChatRequest
from app.orchestration.chat import ChatOrchestrator
from app.runtime.gemini_acp_client import GeminiAcpPromptResult


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


@pytest.mark.asyncio
async def test_gemini_acp_runtime_serializes_prompts_and_logs_reuse(caplog) -> None:
    orchestrator = ChatOrchestrator()
    fake_client = _FakeGeminiAcpClient()
    runtime = {
        "client": fake_client,
        "lock": asyncio.Lock(),
        "initialized": False,
        "session_id": None,
        "model_id": None,
        "waiters": 0,
    }
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
async def test_gemini_acp_runtime_resets_stale_session_when_client_is_unhealthy(caplog) -> None:
    orchestrator = ChatOrchestrator()
    fake_client = _FakeGeminiAcpClient()
    fake_client.healthy = False
    runtime = {
        "client": fake_client,
        "lock": asyncio.Lock(),
        "initialized": True,
        "session_id": "stale-session",
        "model_id": "gemini-2.5-flash",
        "waiters": 0,
    }
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
    assert runtime["session_id"] == "runtime-session"
    assert "gateway.gemini_acp.session_reset" in caplog.text
