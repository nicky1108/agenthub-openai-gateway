import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import pytest

from app.tunnel.agent import LocalGatewayDispatcher, PublicGatewayTunnelAgent
from app.tunnel.protocol import (
    CancelMessage,
    HelloAckMessage,
    RequestMessage,
    build_hello_message,
    parse_tunnel_message,
    verify_hello_message,
)


class FakeWebSocket:
    def __init__(self, incoming: list[str | bytes | None]) -> None:
        self._incoming = list(incoming)
        self.sent: list[str] = []

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> str | bytes:
        await asyncio.sleep(0)
        if not self._incoming:
            raise EOFError
        item = self._incoming.pop(0)
        if item is None:
            raise EOFError
        return item


class StubDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.stream_started = asyncio.Event()
        self.stream_cancelled = asyncio.Event()

    async def introspect_key(self, token: str) -> dict[str, str]:
        self.calls.append(("key.introspect", token))
        return {
            "account_id": "acct_1",
            "workspace_id": "ws_test_account_1",
            "api_key_id": "key_1",
            "status": "active",
        }

    async def list_platform_models(self) -> dict[str, object]:
        self.calls.append(("catalog.platform_models", None))
        return {"object": "list", "data": [{"id": "codex:gpt-5.4"}]}

    async def record_usage_event(self, payload: dict[str, object]) -> dict[str, str]:
        self.calls.append(("usage.record", payload))
        return {"status": "accepted"}

    async def chat_complete(self, *, authorization: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("chat.complete", {"authorization": authorization, "payload": payload}))
        return {"object": "chat.completion", "choices": [{"message": {"content": "ok"}}]}

    async def chat_complete_stream(
        self,
        *,
        authorization: str,
        payload: dict[str, object],
    ) -> AsyncIterator[str]:
        self.calls.append(("chat.complete.stream", {"authorization": authorization, "payload": payload}))
        self.stream_started.set()
        try:
            yield "data: first\n\n"
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.stream_cancelled.set()
            raise


def _hello_ack() -> str:
    return HelloAckMessage(type="hello_ack", device_id="device-local", payload={"accepted": True}).model_dump_json()


@pytest.mark.asyncio
async def test_agent_sends_signed_hello_before_processing_messages() -> None:
    dispatcher = StubDispatcher()
    websocket = FakeWebSocket([_hello_ack(), None])
    agent = PublicGatewayTunnelAgent(
        tunnel_url="wss://public.example.test/internal/tunnel/connect",
        device_id="device-local",
        shared_secret="shared-secret",
        dispatcher=dispatcher,
    )

    await agent.connect_once(websocket=websocket)

    hello = parse_tunnel_message(websocket.sent[0])
    assert hello.type == "hello"
    assert verify_hello_message(hello, secret="shared-secret")


@pytest.mark.asyncio
async def test_agent_dispatches_introspection_and_catalog_requests() -> None:
    dispatcher = StubDispatcher()
    websocket = FakeWebSocket(
        [
          _hello_ack(),
          RequestMessage(
              type="request",
              request_id="req-1",
              device_id="device-local",
              op="key.introspect",
              payload={"token": "agk_test_token"},
          ).model_dump_json(),
          RequestMessage(
              type="request",
              request_id="req-2",
              device_id="device-local",
              op="catalog.platform_models",
              payload={},
          ).model_dump_json(),
          None,
        ]
    )
    agent = PublicGatewayTunnelAgent(
        tunnel_url="wss://public.example.test/internal/tunnel/connect",
        device_id="device-local",
        shared_secret="shared-secret",
        dispatcher=dispatcher,
    )

    await agent.connect_once(websocket=websocket)

    sent = [parse_tunnel_message(message) for message in websocket.sent[1:]]
    assert dispatcher.calls == [
        ("key.introspect", "agk_test_token"),
        ("catalog.platform_models", None),
    ]
    assert [message.type for message in sent] == [
        "response_start",
        "response_end",
        "response_start",
        "response_end",
    ]
    assert sent[1].payload["account_id"] == "acct_1"
    assert sent[3].payload["data"][0]["id"] == "codex:gpt-5.4"


@pytest.mark.asyncio
async def test_agent_dispatches_non_stream_chat_request() -> None:
    dispatcher = StubDispatcher()
    websocket = FakeWebSocket(
        [
            _hello_ack(),
            RequestMessage(
                type="request",
                request_id="req-chat",
                device_id="device-local",
                op="chat.complete",
                payload={
                    "authorization": "Bearer agk_test_token",
                    "request": {
                        "model": "codex:gpt-5.4",
                        "messages": [{"role": "user", "content": "hello"}],
                        "stream": False,
                    },
                },
            ).model_dump_json(),
            None,
        ]
    )
    agent = PublicGatewayTunnelAgent(
        tunnel_url="wss://public.example.test/internal/tunnel/connect",
        device_id="device-local",
        shared_secret="shared-secret",
        dispatcher=dispatcher,
    )

    await agent.connect_once(websocket=websocket)

    sent = [parse_tunnel_message(message) for message in websocket.sent[1:]]
    assert dispatcher.calls[0][0] == "chat.complete"
    assert [message.type for message in sent] == ["response_start", "response_end"]
    assert sent[1].payload["object"] == "chat.completion"


@pytest.mark.asyncio
async def test_agent_streams_chat_chunks() -> None:
    async def stream_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"data: first\n\ndata: [DONE]\n\n")

    dispatcher = LocalGatewayDispatcher(
        base_url="http://local-gateway.test",
        service_token="public-gateway-token",
        transport=httpx.MockTransport(stream_handler),
    )
    websocket = FakeWebSocket(
        [
            _hello_ack(),
            RequestMessage(
                type="request",
                request_id="req-stream",
                device_id="device-local",
                op="chat.complete",
                payload={
                    "authorization": "Bearer agk_test_token",
                    "request": {
                        "model": "codex:gpt-5.4",
                        "messages": [{"role": "user", "content": "hello"}],
                        "stream": True,
                    },
                },
            ).model_dump_json(),
            None,
        ]
    )
    agent = PublicGatewayTunnelAgent(
        tunnel_url="wss://public.example.test/internal/tunnel/connect",
        device_id="device-local",
        shared_secret="shared-secret",
        dispatcher=dispatcher,
    )

    await agent.connect_once(websocket=websocket)

    sent = [parse_tunnel_message(message) for message in websocket.sent[1:]]
    assert [message.type for message in sent] == ["response_start", "response_chunk", "response_end"]
    assert sent[1].payload["chunk"] == "data: first\n\ndata: [DONE]\n\n"


@pytest.mark.asyncio
async def test_agent_cancel_interrupts_stream_request() -> None:
    dispatcher = StubDispatcher()
    websocket = FakeWebSocket(
        [
            _hello_ack(),
            RequestMessage(
                type="request",
                request_id="req-cancel",
                device_id="device-local",
                op="chat.complete",
                payload={
                    "authorization": "Bearer agk_test_token",
                    "request": {
                        "model": "codex:gpt-5.4",
                        "messages": [{"role": "user", "content": "hello"}],
                        "stream": True,
                    },
                },
            ).model_dump_json(),
            CancelMessage(
                type="cancel",
                request_id="req-cancel",
                device_id="device-local",
                payload={"reason": "client_disconnected"},
            ).model_dump_json(),
            None,
        ]
    )
    agent = PublicGatewayTunnelAgent(
        tunnel_url="wss://public.example.test/internal/tunnel/connect",
        device_id="device-local",
        shared_secret="shared-secret",
        dispatcher=dispatcher,
    )

    await agent.connect_once(websocket=websocket)

    sent = [parse_tunnel_message(message) for message in websocket.sent[1:]]
    assert dispatcher.stream_started.is_set()
    assert dispatcher.stream_cancelled.is_set()
    assert sent[0].type == "response_start"
    assert sent[-1].type == "response_error"
    assert sent[-1].payload["code"] == "cancelled"


@pytest.mark.asyncio
async def test_agent_run_forever_retries_after_connection_failure() -> None:
    dispatcher = StubDispatcher()
    agent = PublicGatewayTunnelAgent(
        tunnel_url="wss://public.example.test/internal/tunnel/connect",
        device_id="device-local",
        shared_secret="shared-secret",
        dispatcher=dispatcher,
        reconnect_base_seconds=0.01,
        reconnect_max_seconds=0.02,
    )

    attempts = 0
    sleep_calls: list[float] = []
    stop_event = asyncio.Event()

    async def failing_connect_once(websocket=None):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("connect failed")

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        stop_event.set()

    agent.connect_once = failing_connect_once  # type: ignore[method-assign]

    await agent.run_forever(stop_event=stop_event, sleep_fn=fake_sleep)

    assert attempts == 1
    assert sleep_calls == [0.01]
