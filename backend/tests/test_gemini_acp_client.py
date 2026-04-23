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


@pytest.mark.asyncio
async def test_gemini_acp_client_restarts_after_process_exit() -> None:
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
        await client.initialize()
        assert client._process is not None
        first_pid = client._process.pid
        client._process.terminate()
        await client._process.wait()
        if client._reader_task is not None:
            await client._reader_task

        await client.initialize()
        assert client._process is not None
        assert client._process.pid != first_pid
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_gemini_acp_client_fails_fast_when_process_exits_mid_prompt() -> None:
    from app.runtime.gemini_acp_client import GeminiAcpClient

    fixture = pathlib.Path(__file__).parent / "fixtures" / "gemini_acp_crash_stub.py"
    command = str(pathlib.Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python")
    client = GeminiAcpClient(
        command=command,
        args=[str(fixture)],
        env={},
        cwd=None,
        read_timeout_seconds=5,
    )

    try:
        await client.initialize()
        await client.new_session("/tmp")
        with pytest.raises(RuntimeError, match="gemini acp process exited"):
            await client.prompt("crash-session", "hello")
    finally:
        await client.close()
