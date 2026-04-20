import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from app.adapters.base import ChatRequest


class CodexCliAdapter:
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
        return "\n".join(
            f"{str(message.get('role', 'user')).upper()}: {str(message.get('content', ''))}"
            for message in request.messages
        )

    async def _run(self, request: ChatRequest) -> list[dict[str, Any]]:
        process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            "exec",
            "-C",
            self.cwd or ".",
            "--skip-git-repo-check",
            self._prompt(request),
            "--json",
            "-m",
            request.provider_model,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=self.env or None,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.read_timeout_seconds,
            )
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            process.kill()
            await process.communicate()
            if isinstance(exc, asyncio.TimeoutError):
                raise TimeoutError("codex cli timed out") from exc
            raise
        if process.returncode != 0:
            raise RuntimeError(stderr.decode() or "codex cli failed")

        events: list[dict[str, Any]] = []
        for line in stdout.decode().splitlines():
            if not line.strip():
                continue
            if not line.lstrip().startswith("{"):
                continue
            events.append(json.loads(line))
        return events

    async def chat(self, request: ChatRequest) -> dict[str, Any]:
        events = await self._run(request)
        message_text = ""
        item_id = "codex-cli"
        for event in events:
            if event.get("type") == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message":
                    message_text = item.get("text", "")
                    item_id = item.get("id", item_id)
        return {
            "id": item_id,
            "object": "chat.completion",
            "model": f"{request.provider_name}:{request.provider_model}",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": message_text},
                    "finish_reason": "stop",
                }
            ],
        }

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[str]:
        events = await self._run(request)
        item_id = "codex-cli"
        emitted = False
        for event in events:
            if event.get("type") == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message":
                    item_id = item.get("id", item_id)
                    chunk = {
                        "id": item_id,
                        "object": "chat.completion.chunk",
                        "model": f"{request.provider_name}:{request.provider_model}",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": item.get("text", "")},
                                "finish_reason": "stop",
                            }
                        ],
                    }
                    emitted = True
                    yield f"data: {json.dumps(chunk)}\n\n"
        if emitted:
            yield "data: [DONE]\n\n"
