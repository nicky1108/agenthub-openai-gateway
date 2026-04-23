from __future__ import annotations

import pathlib

import pytest


@pytest.mark.asyncio
async def test_gemini_acp_client_initialize_new_session_and_prompt() -> None:
    from app.runtime.gemini_acp_client import GeminiAcpClient

    fixture = pathlib.Path(__file__).parent / "fixtures" / "gemini_acp_stub.py"
    command = str(pathlib.Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python")
    client = GeminiAcpClient(
        command=command,
        args=[str(fixture)],
        env={},
        cwd=None,
        read_timeout_seconds=5,
    )

    try:
        initialize_result = await client.initialize()
        assert initialize_result["protocolVersion"] == 1

        session_result = await client.new_session("/tmp")
        assert session_result["sessionId"] == "stub-session"

        prompt_result = await client.prompt("stub-session", "Say OK and nothing else.")
        assert prompt_result.result["stopReason"] == "end_turn"
        assert prompt_result.updates[0]["update"]["content"]["text"] == "OK"
    finally:
        await client.close()
