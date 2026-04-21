import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from app.adapters.base import ChatRequest


class GeminiCliAdapter:
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

    def _prompt(self, request: ChatRequest) -> str:
        lines: list[str] = []
        for message in request.messages:
            role = str(message.get("role", "user")).upper()
            content = str(message.get("content", ""))
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    async def _spawn(self, extra_args: list[str]) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            *extra_args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=self.env or None,
        )

    async def _run(self, extra_args: list[str]) -> str:
        process = await self._spawn(extra_args)
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.read_timeout_seconds,
            )
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            process.kill()
            await process.communicate()
            if isinstance(exc, asyncio.TimeoutError):
                raise TimeoutError("gemini cli timed out") from exc
            raise
        if process.returncode != 0:
            raise RuntimeError(stderr.decode() or "gemini cli failed")
        return stdout.decode()

    async def chat(self, request: ChatRequest) -> dict[str, Any]:
        raw = await self._run(
            [
                "-p",
                self._prompt(request),
                "--output-format",
                "json",
                "-m",
                request.provider_model,
            ]
        )
        payload = json.loads(raw)
        content = payload.get("response", "")
        return {
            "id": payload.get("session_id", "gemini-cli"),
            "object": "chat.completion",
            "model": f"{request.provider_name}:{request.provider_model}",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
        }

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[str]:
        process = await self._spawn(
            [
                "-p",
                self._prompt(request),
                "--output-format",
                "stream-json",
                "-m",
                request.provider_model,
            ]
        )
        stderr_task = asyncio.create_task(process.stderr.read() if process.stderr is not None else asyncio.sleep(0, result=b""))
        session_id = "gemini-cli"
        emitted = False
        try:
            while True:
                assert process.stdout is not None
                line = await asyncio.wait_for(process.stdout.readline(), timeout=self.read_timeout_seconds)
                if not line:
                    break
                text = line.decode().strip()
                if not text:
                    continue
                payload = json.loads(text)
                if payload.get("session_id"):
                    session_id = payload.get("session_id", session_id)
                if payload.get("type") == "message" and payload.get("role") == "assistant":
                    chunk = {
                        "id": session_id,
                        "object": "chat.completion.chunk",
                        "model": f"{request.provider_name}:{request.provider_model}",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": payload.get("content", "")},
                                "finish_reason": None,
                            }
                        ],
                    }
                    emitted = True
                    yield f"data: {json.dumps(chunk)}\n\n"
                if payload.get("type") == "result":
                    break
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            process.kill()
            await process.communicate()
            await stderr_task
            if isinstance(exc, asyncio.TimeoutError):
                raise TimeoutError("gemini cli timed out") from exc
            raise
        stderr = (await stderr_task).decode()
        return_code = await process.wait()
        if return_code != 0:
            raise RuntimeError(stderr or "gemini cli failed")
        if emitted:
            chunk = {
                "id": session_id,
                "object": "chat.completion.chunk",
                "model": f"{request.provider_name}:{request.provider_model}",
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }
                ],
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"
