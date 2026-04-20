import httpx
import pytest

from app.adapters.base import ChatRequest
from app.adapters.http.openai_compatible import OpenAICompatibleHttpAdapter


@pytest.mark.asyncio
async def test_http_adapter_posts_to_upstream_openai_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "id": "upstream-1",
                "object": "chat.completion",
                "model": "codex:gpt-5.4",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "real-http-response"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    adapter = OpenAICompatibleHttpAdapter(
        base_url="http://upstream.test",
        api_key="test-key",
        headers={},
        transport=httpx.MockTransport(handler),
    )
    result = await adapter.chat(
        ChatRequest(
            provider_name="codex",
            provider_model="gpt-5.4",
            messages=[{"role": "user", "content": "hello"}],
            stream=False,
        )
    )

    assert result["choices"][0]["message"]["content"] == "real-http-response"
