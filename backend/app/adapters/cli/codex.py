import asyncio
import json
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Any

from app.adapters.base import ChatRequest
from app.runtime.logging import elapsed_ms, log_gateway_event


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

    async def _spawn(self, request: ChatRequest) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            "exec",
            "-C",
            self.cwd or ".",
            "--skip-git-repo-check",
            "--json",
            "--ephemeral",
            "--ignore-rules",
            "-m",
            request.provider_model,
            self._prompt(request),
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

    @staticmethod
    def _usage_payload(event: dict[str, Any]) -> dict[str, Any] | None:
        usage = event.get("usage")
        if not isinstance(usage, dict):
            return None
        return {
            "prompt_tokens": int(usage.get("input_tokens") or 0),
            "completion_tokens": int(usage.get("output_tokens") or 0),
            "prompt_tokens_details": {"cached_tokens": 0},
        }

    async def _collect_events(self, request: ChatRequest) -> list[dict[str, Any]]:
        started_at = perf_counter()
        process = await self._spawn(request)
        self._log_cli_event("gateway.cli.spawn", request, mode="chat", elapsed_since=started_at)
        stderr_task = asyncio.create_task(process.stderr.read() if process.stderr is not None else asyncio.sleep(0, result=b""))
        try:
            events: list[dict[str, Any]] = []
            first_output_logged = False
            while True:
                assert process.stdout is not None
                line = await asyncio.wait_for(process.stdout.readline(), timeout=self.read_timeout_seconds)
                if not line:
                    break
                if not first_output_logged:
                    self._log_cli_event("gateway.cli.first_output", request, mode="chat", elapsed_since=started_at)
                    first_output_logged = True
                text = line.decode().strip()
                if not text or not text.lstrip().startswith("{"):
                    continue
                events.append(json.loads(text))
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            process.kill()
            await process.wait()
            await stderr_task
            if isinstance(exc, asyncio.TimeoutError):
                raise TimeoutError("codex cli timed out") from exc
            raise
        stderr = (await stderr_task).decode()
        return_code = await process.wait()
        if return_code != 0:
            raise RuntimeError(stderr or "codex cli failed")
        self._log_cli_event("gateway.cli.complete", request, mode="chat", elapsed_since=started_at)
        return events

    async def chat(self, request: ChatRequest) -> dict[str, Any]:
        events = await self._collect_events(request)
        message_text = ""
        item_id = "codex-cli"
        usage_payload: dict[str, Any] | None = None
        for event in events:
            if event.get("type") == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message":
                    message_text = item.get("text", "")
                    item_id = item.get("id", item_id)
            if event.get("type") == "turn.completed":
                usage_payload = self._usage_payload(event)
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
            **({"usage": usage_payload} if usage_payload is not None else {}),
        }

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[str]:
        started_at = perf_counter()
        process = await self._spawn(request)
        self._log_cli_event("gateway.cli.spawn", request, mode="stream", elapsed_since=started_at)
        stderr_task = asyncio.create_task(process.stderr.read() if process.stderr is not None else asyncio.sleep(0, result=b""))
        item_id = "codex-cli"
        emitted = False
        usage_payload: dict[str, Any] | None = None
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
                if not text or not text.lstrip().startswith("{"):
                    continue
                event = json.loads(text)
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
                                    "finish_reason": None,
                                }
                            ],
                        }
                        emitted = True
                        yield f"data: {json.dumps(chunk)}\n\n"
                if event.get("type") == "turn.completed":
                    usage_payload = self._usage_payload(event)
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            process.kill()
            await process.wait()
            await stderr_task
            if isinstance(exc, asyncio.TimeoutError):
                raise TimeoutError("codex cli timed out") from exc
            raise
        stderr = (await stderr_task).decode()
        return_code = await process.wait()
        if return_code != 0:
            raise RuntimeError(stderr or "codex cli failed")
        self._log_cli_event("gateway.cli.complete", request, mode="stream", elapsed_since=started_at)
        if emitted:
            chunk = {
                "id": item_id,
                "object": "chat.completion.chunk",
                "model": f"{request.provider_name}:{request.provider_model}",
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }
                ],
                **({"usage": usage_payload} if usage_payload is not None else {}),
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"
