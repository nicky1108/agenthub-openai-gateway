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
        }
