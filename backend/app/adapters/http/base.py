from collections.abc import AsyncIterator

from app.adapters.base import ChatRequest


class MockHttpAdapter:
    async def chat(self, request: ChatRequest) -> dict[str, object]:
        return {
            "id": "chatcmpl-http-1",
            "object": "chat.completion",
            "model": f"{request.provider_name}:{request.provider_model}",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "mocked-http-response"},
                    "finish_reason": "stop",
                }
            ],
        }

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[str]:
        model = f"{request.provider_name}:{request.provider_model}"
        yield (
            'data: {"id":"chatcmpl-http-1","object":"chat.completion.chunk",'
            f'"model":"{model}","choices":[{{"index":0,"delta":{{"content":"mocked-"}},"finish_reason":null}}]}}\n\n'
        )
        yield (
            'data: {"id":"chatcmpl-http-1","object":"chat.completion.chunk",'
            f'"model":"{model}","choices":[{{"index":0,"delta":{{"content":"http-response"}},"finish_reason":"stop"}}]}}\n\n'
        )
        yield "data: [DONE]\n\n"
