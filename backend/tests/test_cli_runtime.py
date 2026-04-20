import pathlib

import pytest

from app.adapters.base import ChatRequest
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
    chunks = [chunk async for chunk in adapter.stream_chat(request)]

    assert result["choices"][0]["message"]["content"] == "gemini:gemini-2.5-flash:ok"
    assert "gemini-stream" in chunks[0]
    assert chunks[-1] == "data: [DONE]\n\n"
