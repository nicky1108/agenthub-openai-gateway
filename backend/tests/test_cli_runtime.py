import pathlib
import asyncio
import logging

import pytest

from app.adapters.base import ChatRequest
from app.adapters.cli.codex import CodexCliAdapter
from app.adapters.cli.gemini import GeminiCliAdapter
from app.adapters.cli.process import ProcessCliAdapter


@pytest.mark.asyncio
async def test_cli_adapter_executes_subprocess_and_parses_json() -> None:
    fixture = pathlib.Path(__file__).parent / "fixtures" / "echo_chat.py"
    adapter = ProcessCliAdapter(
        command=str(pathlib.Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"),
        args=[str(fixture)],
        env={},
        cwd=None,
        read_timeout_seconds=5,
    )

    result = await adapter.chat(
        ChatRequest(
            provider_name="gemini",
            provider_model="gemini-2.5-pro",
            messages=[{"role": "user", "content": "hello"}],
            stream=False,
        )
    )

    assert result["choices"][0]["message"]["content"] == "real-cli-response"


@pytest.mark.asyncio
async def test_gemini_cli_adapter_parses_json_and_stream_output() -> None:
    fixture = pathlib.Path(__file__).parent / "fixtures" / "gemini_stub.py"
    command = str(pathlib.Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python")
    adapter = GeminiCliAdapter(
        command=command,
        args=[str(fixture)],
        env={},
        cwd=None,
        read_timeout_seconds=5,
    )
    request = ChatRequest(
        provider_name="gemini",
        provider_model="gemini-2.5-flash",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
    )

    result = await adapter.chat(request)
    stream = adapter.stream_chat(request)
    first_chunk = await asyncio.wait_for(anext(stream), timeout=0.25)
    second_chunk = await asyncio.wait_for(anext(stream), timeout=1.0)
    done_chunk = await asyncio.wait_for(anext(stream), timeout=1.0)

    assert result["choices"][0]["message"]["content"] == "gemini:gemini-2.5-flash:ok"
    assert "gemini-stream" in first_chunk
    assert '"finish_reason": "stop"' in second_chunk or '"finish_reason":"stop"' in second_chunk
    assert done_chunk == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_gemini_cli_adapter_logs_spawn_first_output_and_complete(caplog) -> None:
    fixture = pathlib.Path(__file__).parent / "fixtures" / "gemini_stub.py"
    command = str(pathlib.Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python")
    adapter = GeminiCliAdapter(
        command=command,
        args=[str(fixture)],
        env={},
        cwd=None,
        read_timeout_seconds=5,
    )
    request = ChatRequest(
        provider_name="gemini",
        provider_model="gemini-2.5-flash",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
        request_id="req-gemini-log",
    )
    caplog.set_level(logging.INFO, logger="agenthub.gateway")

    await adapter.chat(request)

    assert "gateway.cli.spawn" in caplog.text
    assert "gateway.cli.first_output" in caplog.text
    assert "gateway.cli.complete" in caplog.text
    assert "request_id='req-gemini-log'" in caplog.text
    assert "mode='chat'" in caplog.text


@pytest.mark.asyncio
async def test_codex_cli_adapter_parses_jsonl_events() -> None:
    fixture = pathlib.Path(__file__).parent / "fixtures" / "codex_stub.py"
    command = str(pathlib.Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python")
    adapter = CodexCliAdapter(
        command=command,
        args=[str(fixture)],
        env={},
        cwd=str(pathlib.Path(__file__).resolve().parents[1].parent),
        read_timeout_seconds=5,
    )
    request = ChatRequest(
        provider_name="codex",
        provider_model="gpt-5.4",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
    )

    result = await adapter.chat(request)
    stream = adapter.stream_chat(request)
    first_chunk = await asyncio.wait_for(anext(stream), timeout=0.25)
    second_chunk = await asyncio.wait_for(anext(stream), timeout=1.0)
    done_chunk = await asyncio.wait_for(anext(stream), timeout=1.0)

    assert result["choices"][0]["message"]["content"] == "codex:gpt-5.4:ok"
    assert "codex:gpt-5.4:ok" in first_chunk
    assert '"finish_reason": "stop"' in second_chunk or '"finish_reason":"stop"' in second_chunk
    assert done_chunk == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_codex_cli_adapter_logs_spawn_first_output_and_complete(caplog) -> None:
    fixture = pathlib.Path(__file__).parent / "fixtures" / "codex_stub.py"
    command = str(pathlib.Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python")
    adapter = CodexCliAdapter(
        command=command,
        args=[str(fixture)],
        env={},
        cwd=str(pathlib.Path(__file__).resolve().parents[1].parent),
        read_timeout_seconds=5,
    )
    request = ChatRequest(
        provider_name="codex",
        provider_model="gpt-5.4",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
        request_id="req-codex-log",
    )
    caplog.set_level(logging.INFO, logger="agenthub.gateway")

    await adapter.chat(request)

    assert "gateway.cli.spawn" in caplog.text
    assert "gateway.cli.first_output" in caplog.text
    assert "gateway.cli.complete" in caplog.text
    assert "request_id='req-codex-log'" in caplog.text
    assert "mode='chat'" in caplog.text


@pytest.mark.asyncio
async def test_codex_cli_adapter_reports_stdout_error_when_stderr_is_empty(tmp_path) -> None:
    fixture = tmp_path / "codex_error.py"
    fixture.write_text(
        "import json, sys\n"
        "print(json.dumps({'type': 'error', 'message': 'not authenticated'}))\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    command = str(pathlib.Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python")
    adapter = CodexCliAdapter(
        command=command,
        args=[str(fixture)],
        env={},
        cwd=str(pathlib.Path(__file__).resolve().parents[1].parent),
        read_timeout_seconds=5,
    )
    request = ChatRequest(
        provider_name="codex",
        provider_model="gpt-5.4",
        messages=[{"role": "user", "content": "hello"}],
        stream=False,
    )

    with pytest.raises(RuntimeError, match="codex cli failed with exit code 1: not authenticated"):
        await adapter.chat(request)
