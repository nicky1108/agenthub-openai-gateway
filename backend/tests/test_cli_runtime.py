import pathlib

import pytest

from app.adapters.base import ChatRequest
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
