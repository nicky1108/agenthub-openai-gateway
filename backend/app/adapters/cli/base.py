import json
from collections.abc import AsyncIterator

from app.adapters.base import ChatRequest


class MockCliAdapter:
    async def chat(self, request: ChatRequest) -> dict[str, object]:
        return {
            "id": "chatcmpl-cli-1",
            "object": "chat.completion",
            "model": f"{request.provider_name}:{request.provider_model}",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "mocked-cli-response"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "prompt_tokens_details": {"cached_tokens": 0},
            },
        }

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[str]:
        model = f"{request.provider_name}:{request.provider_model}"
        yield (
            "data: "
            + json.dumps(
                {
                    "id": "chatcmpl-cli-1",
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": "mocked-"},
                            "finish_reason": None,
                        }
                    ],
                },
                separators=(",", ":"),
            )
            + "\n\n"
        )
        yield (
            "data: "
            + json.dumps(
                {
                    "id": "chatcmpl-cli-1",
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": "cli-response"},
                            "finish_reason": "stop",
                        }
                    ],
                },
                separators=(",", ":"),
            )
            + "\n\n"
        )
        yield "data: [DONE]\n\n"
