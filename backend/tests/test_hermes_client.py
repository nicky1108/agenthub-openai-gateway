import json

import httpx
import pytest

from app.services.hermes_client import (
    HermesClient,
    HermesRequest,
    HermesResponseEvent,
    extract_hermes_output_text,
)


@pytest.mark.asyncio
async def test_hermes_client_streams_text_and_completion() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        assert request.headers["authorization"] == "Bearer test-key"
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "hermes-agent"
        assert body["input"] == "run task"
        assert body["stream"] is True
        stream = "\n\n".join(
            [
                'data: {"type":"response.output_text.delta","delta":"hello"}',
                'data: {"type":"response.output_text.delta","delta":" world"}',
                'data: {"type":"response.completed","response":{"id":"resp-1","output_text":"hello world"}}',
                "data: [DONE]",
            ]
        )
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=stream)

    client = HermesClient(
        base_url="http://hermes.local/v1",
        api_key="test-key",
        model="hermes-agent",
        transport=httpx.MockTransport(handler),
    )

    events = [
        event
        async for event in client.stream_response(
            HermesRequest(input_text="run task", conversation="acct:default", metadata={"source": "test"})
        )
    ]

    assert [event.type for event in events] == [
        "response.output_text.delta",
        "response.output_text.delta",
        "response.completed",
    ]
    assert events[0].payload == {"delta": "hello"}
    assert events[-1].payload["response"]["id"] == "resp-1"


def test_extract_hermes_output_text_supports_output_array() -> None:
    payload = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "first"},
                    {"type": "text", "text": "second"},
                ],
            }
        ]
    }

    assert extract_hermes_output_text(payload) == "first\nsecond"


def test_hermes_response_event_rejects_empty_type() -> None:
    with pytest.raises(ValueError, match="event type is required"):
        HermesResponseEvent(type="", payload={})
