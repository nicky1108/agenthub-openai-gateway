import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from app.adapters.base import ChatRequest


class ProcessCliAdapter:
    def __init__(
        self,
        command: str,
        args: list[str],
        env: dict[str, str],
        cwd: str | None,
        read_timeout_seconds: int,
    ) -> None:
        self.command = command
        self.args = args
        self.env = env
        self.cwd = cwd
        self.read_timeout_seconds = read_timeout_seconds

    async def chat(self, request: ChatRequest) -> dict[str, Any]:
        process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=self.env or None,
        )
        payload = json.dumps(
            {
                "model": f"{request.provider_name}:{request.provider_model}",
                "messages": request.messages,
                "stream": False,
            }
        ).encode()
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(payload),
                timeout=self.read_timeout_seconds,
            )
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            process.kill()
            await process.communicate()
            if isinstance(exc, asyncio.TimeoutError):
                raise TimeoutError("cli adapter timed out") from exc
            raise
        if process.returncode != 0:
            raise RuntimeError(stderr.decode() or "cli adapter failed")
        return json.loads(stdout.decode())

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[str]:
        result = await self.chat(request)
        content = result["choices"][0]["message"]["content"]
        model = result["model"]
        chunk = {
            "id": result["id"],
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": content},
                    "finish_reason": "stop",
                }
            ],
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"
