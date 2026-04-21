import pathlib
import asyncio

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
