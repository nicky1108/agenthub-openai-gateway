from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GeminiAcpPromptResult:
    result: dict[str, Any]
    updates: list[dict[str, Any]]


class GeminiAcpClient:
    def __init__(
        self,
        *,
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
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_request_id = 1
        self._prompt_updates: dict[str, list[dict[str, Any]]] = {}

    def _is_process_healthy(self) -> bool:
        return (
            self._process is not None
            and self._process.returncode is None
            and self._reader_task is not None
            and not self._reader_task.done()
        )

    def _reset_handles(self) -> None:
        self._process = None
        self._reader_task = None

    async def _ensure_started(self) -> None:
        if self._is_process_healthy():
            return
        self._reset_handles()
        self._process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=self.env or None,
        )
        self._reader_task = asyncio.create_task(self._read_stdout())

    async def _read_stdout(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None
        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                payload = json.loads(line.decode())
                if "id" in payload:
                    request_id = int(payload["id"])
                    future = self._pending.pop(request_id, None)
                    if future is None:
                        continue
                    if "error" in payload:
                        future.set_exception(RuntimeError(str(payload["error"])))
                    else:
                        future.set_result(payload["result"])
                    continue
                if payload.get("method") == "session/update":
                    params = payload.get("params") or {}
                    session_id = params.get("sessionId")
                    if isinstance(session_id, str) and session_id in self._prompt_updates:
                        self._prompt_updates[session_id].append(params)
        finally:
            while self._pending:
                _request_id, future = self._pending.popitem()
                if not future.done():
                    future.set_exception(RuntimeError("gemini acp process exited"))
            self._reader_task = None

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_started()
        assert self._process is not None
        assert self._process.stdin is not None
        request_id = self._next_request_id
        self._next_request_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        self._process.stdin.write((json.dumps(message) + "\n").encode())
        try:
            await self._process.stdin.drain()
        except (ConnectionResetError, BrokenPipeError) as exc:
            self._pending.pop(request_id, None)
            raise RuntimeError("gemini acp process exited") from exc
        return await asyncio.wait_for(future, timeout=self.read_timeout_seconds)

    async def initialize(self) -> dict[str, Any]:
        return await self._request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False},
                    "terminal": False,
                    "auth": {"terminal": False},
                },
            },
        )

    async def new_session(self, cwd: str) -> dict[str, Any]:
        return await self._request("session/new", {"cwd": cwd, "mcpServers": []})

    async def set_model(self, session_id: str, model_id: str) -> dict[str, Any]:
        return await self._request("session/set_model", {"sessionId": session_id, "modelId": model_id})

    async def prompt(self, session_id: str, text: str) -> GeminiAcpPromptResult:
        self._prompt_updates[session_id] = []
        try:
            result = await self._request(
                "session/prompt",
                {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": text}],
                },
            )
            return GeminiAcpPromptResult(result=result, updates=list(self._prompt_updates[session_id]))
        finally:
            self._prompt_updates.pop(session_id, None)

    async def close(self) -> None:
        if self._process is None:
            return
        if self._process.stdin is not None:
            try:
                self._process.stdin.close()
            except Exception:
                pass
        if self._process.returncode is None:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(self._process.wait(), timeout=3)
        except asyncio.TimeoutError:
            self._process.kill()
            await self._process.wait()
        if self._reader_task is not None:
            await self._reader_task
        self._reset_handles()
