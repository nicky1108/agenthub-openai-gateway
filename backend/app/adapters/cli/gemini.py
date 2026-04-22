import asyncio
import json
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Any

from app.adapters.base import ChatRequest
from app.runtime.logging import elapsed_ms, log_gateway_event


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

    def _log_cli_event(
        self,
        event: str,
        request: ChatRequest,
        *,
        mode: str,
        elapsed_since: float,
    ) -> None:
        log_gateway_event(
            event,
            request_id=request.request_id,
            provider=request.provider_name,
            model=f"{request.provider_name}:{request.provider_model}",
            mode=mode,
            elapsed_ms=elapsed_ms(elapsed_since),
        )

    async def _run(self, request: ChatRequest, extra_args: list[str], *, mode: str) -> str:
        started_at = perf_counter()
        process = await self._spawn(extra_args)
        self._log_cli_event("gateway.cli.spawn", request, mode=mode, elapsed_since=started_at)
        stderr_task = asyncio.create_task(process.stderr.read() if process.stderr is not None else asyncio.sleep(0, result=b""))
        try:
            stdout_lines: list[str] = []
            first_output_logged = False
            while True:
                assert process.stdout is not None
                line = await asyncio.wait_for(process.stdout.readline(), timeout=self.read_timeout_seconds)
                if not line:
                    break
                if not first_output_logged:
                    self._log_cli_event("gateway.cli.first_output", request, mode=mode, elapsed_since=started_at)
                    first_output_logged = True
                stdout_lines.append(line.decode())
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            process.kill()
            await process.wait()
            await stderr_task
            if isinstance(exc, asyncio.TimeoutError):
                raise TimeoutError("gemini cli timed out") from exc
            raise
        stderr = (await stderr_task).decode()
        return_code = await process.wait()
        if return_code != 0:
            raise RuntimeError(stderr or "gemini cli failed")
        self._log_cli_event("gateway.cli.complete", request, mode=mode, elapsed_since=started_at)
        return "".join(stdout_lines)

    async def chat(self, request: ChatRequest) -> dict[str, Any]:
        raw = await self._run(
            request,
            [
                "-p",
                self._prompt(request),
                "--output-format",
                "json",
                "-m",
                request.provider_model,
            ],
            mode="chat",
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
        started_at = perf_counter()
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
        self._log_cli_event("gateway.cli.spawn", request, mode="stream", elapsed_since=started_at)
        stderr_task = asyncio.create_task(process.stderr.read() if process.stderr is not None else asyncio.sleep(0, result=b""))
        session_id = "gemini-cli"
        emitted = False
        first_output_logged = False
        try:
            while True:
                assert process.stdout is not None
                line = await asyncio.wait_for(process.stdout.readline(), timeout=self.read_timeout_seconds)
                if not line:
                    break
                if not first_output_logged:
                    self._log_cli_event("gateway.cli.first_output", request, mode="stream", elapsed_since=started_at)
                    first_output_logged = True
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
            await process.wait()
            await stderr_task
            if isinstance(exc, asyncio.TimeoutError):
                raise TimeoutError("gemini cli timed out") from exc
            raise
        stderr = (await stderr_task).decode()
        return_code = await process.wait()
        if return_code != 0:
            raise RuntimeError(stderr or "gemini cli failed")
        self._log_cli_event("gateway.cli.complete", request, mode="stream", elapsed_since=started_at)
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
