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
