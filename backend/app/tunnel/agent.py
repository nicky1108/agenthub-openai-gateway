from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from app.core.settings import Settings
from app.tunnel.protocol import (
    CancelMessage,
    HelloAckMessage,
    PingMessage,
    PongMessage,
    RequestMessage,
    ResponseChunkMessage,
    ResponseEndMessage,
    ResponseErrorMessage,
    ResponseStartMessage,
    build_hello_message,
    parse_tunnel_message,
    serialize_tunnel_message,
)


class LocalGatewayDispatcher:
    def __init__(
        self,
        *,
        base_url: str,
        service_token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._service_token = service_token
        self._transport = transport

    async def introspect_key(self, token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self._base_url, transport=self._transport, timeout=30.0) as client:
            response = await client.post(
                "/internal/public-gateway/introspect-key",
                headers={"x-public-gateway-token": self._service_token},
                json={"token": token},
            )
            response.raise_for_status()
            return response.json()

    async def list_platform_models(self) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self._base_url, transport=self._transport, timeout=30.0) as client:
            response = await client.get(
                "/internal/public-gateway/models",
                headers={"x-public-gateway-token": self._service_token},
            )
            response.raise_for_status()
            return response.json()

    async def record_usage_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self._base_url, transport=self._transport, timeout=30.0) as client:
            response = await client.post(
                "/internal/public-gateway/usage-events",
                headers={"x-public-gateway-token": self._service_token},
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def sync_account_upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self._base_url, transport=self._transport, timeout=30.0) as client:
            response = await client.post(
                "/internal/public-gateway/accounts/upsert",
                headers={"x-public-gateway-token": self._service_token},
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def get_account_mirror_status(self, public_account_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self._base_url, transport=self._transport, timeout=30.0) as client:
            response = await client.get(
                f"/internal/public-gateway/accounts/{public_account_id}/mirror",
                headers={"x-public-gateway-token": self._service_token},
            )
            response.raise_for_status()
            return response.json()

    async def sync_api_key_upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self._base_url, transport=self._transport, timeout=30.0) as client:
            response = await client.post(
                "/internal/public-gateway/api-keys/upsert",
                headers={"x-public-gateway-token": self._service_token},
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def sync_api_key_revoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self._base_url, transport=self._transport, timeout=30.0) as client:
            response = await client.post(
                "/internal/public-gateway/api-keys/revoke",
                headers={"x-public-gateway-token": self._service_token},
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def chat_complete(self, *, authorization: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self._base_url, transport=self._transport, timeout=120.0) as client:
            response = await client.post(
                "/v1/chat/completions",
                headers={"authorization": authorization},
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def chat_complete_stream(
        self,
        *,
        authorization: str,
        payload: dict[str, Any],
    ) -> AsyncIterator[str]:
        async with httpx.AsyncClient(base_url=self._base_url, transport=self._transport, timeout=120.0) as client:
            async with client.stream(
                "POST",
                "/v1/chat/completions",
                headers={"authorization": authorization},
                json=payload,
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_text():
                    if chunk:
                        yield chunk


class PublicGatewayTunnelAgent:
    def __init__(
        self,
        *,
        tunnel_url: str,
        device_id: str,
        shared_secret: str,
        dispatcher: LocalGatewayDispatcher,
        connect_fn: Callable[..., Awaitable[Any]] | None = None,
        reconnect_base_seconds: float = 1.0,
        reconnect_max_seconds: float = 15.0,
    ) -> None:
        self.tunnel_url = tunnel_url
        self.device_id = device_id
        self.shared_secret = shared_secret
        self.dispatcher = dispatcher
        self._connect_fn = connect_fn or connect
        self.reconnect_base_seconds = reconnect_base_seconds
        self.reconnect_max_seconds = reconnect_max_seconds
        self._send_lock = asyncio.Lock()
        self._inflight: dict[str, asyncio.Task[None]] = {}

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        connect_fn: Callable[..., Awaitable[Any]] | None = None,
    ) -> "PublicGatewayTunnelAgent":
        if not settings.public_gateway_tunnel_url:
            raise ValueError("public_gateway_tunnel_url is required")
        if not settings.public_gateway_tunnel_device_id:
            raise ValueError("public_gateway_tunnel_device_id is required")
        if not settings.public_gateway_tunnel_secret:
            raise ValueError("public_gateway_tunnel_secret is required")
        return cls(
            tunnel_url=settings.public_gateway_tunnel_url,
            device_id=settings.public_gateway_tunnel_device_id,
            shared_secret=settings.public_gateway_tunnel_secret,
            dispatcher=LocalGatewayDispatcher(
                base_url=f"http://{settings.openai_gateway_host}:{settings.openai_gateway_port}",
                service_token=settings.public_gateway_service_token,
                transport=transport,
            ),
            connect_fn=connect_fn,
            reconnect_base_seconds=settings.public_gateway_tunnel_reconnect_base_seconds,
            reconnect_max_seconds=settings.public_gateway_tunnel_reconnect_max_seconds,
        )

    async def run_forever(
        self,
        *,
        stop_event: asyncio.Event | None = None,
        sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        backoff = self.reconnect_base_seconds
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            try:
                await self.connect_once()
                backoff = self.reconnect_base_seconds
            except asyncio.CancelledError:
                raise
            except Exception:
                if stop_event is not None and stop_event.is_set():
                    return
                await sleep_fn(backoff)
                backoff = min(backoff * 2, self.reconnect_max_seconds)

    async def connect_once(self, websocket: Any | None = None) -> None:
        if websocket is not None:
            await self.handle_connection(websocket)
            return

        async with self._connect_fn(self.tunnel_url, ping_interval=None) as live_websocket:
            await self.handle_connection(live_websocket)

    async def handle_connection(self, websocket: Any) -> None:
        await self._send(
            websocket,
            build_hello_message(device_id=self.device_id, secret=self.shared_secret),
        )
        hello_ack = parse_tunnel_message(await websocket.recv())
        if not isinstance(hello_ack, HelloAckMessage):
            raise RuntimeError("expected hello_ack")

        try:
            while True:
                raw = await websocket.recv()
                message = parse_tunnel_message(raw)
                if isinstance(message, PingMessage):
                    await self._send(
                        websocket,
                        PongMessage(type="pong", device_id=self.device_id, payload=message.payload),
                    )
                    continue
                if isinstance(message, CancelMessage):
                    task = self._inflight.pop(message.request_id, None)
                    if task is not None:
                        task.cancel()
                    continue
                if isinstance(message, RequestMessage):
                    task = asyncio.create_task(self._handle_request(websocket, message))
                    self._inflight[message.request_id] = task
        except (EOFError, ConnectionClosed):
            for task in list(self._inflight.values()):
                task.cancel()
            self._inflight.clear()

    async def _handle_request(self, websocket: Any, message: RequestMessage) -> None:
        try:
            await self._send(
                websocket,
                ResponseStartMessage(
                    type="response_start",
                    request_id=message.request_id,
                    device_id=self.device_id,
                    op=message.op,
                    payload={},
                ),
            )
            if message.op == "key.introspect":
                body = message.payload.get("body", {})
                if not isinstance(body, dict):
                    raise ValueError("invalid key.introspect payload")
                result = await self.dispatcher.introspect_key(str(body["token"]))
                await self._send(
                    websocket,
                    ResponseEndMessage(
                        type="response_end",
                        request_id=message.request_id,
                        device_id=self.device_id,
                        op=message.op,
                        payload={"status_code": 200, "body": result},
                    ),
                )
                return
            if message.op == "catalog.platform_models":
                result = await self.dispatcher.list_platform_models()
                await self._send(
                    websocket,
                    ResponseEndMessage(
                        type="response_end",
                        request_id=message.request_id,
                        device_id=self.device_id,
                        op=message.op,
                        payload={"status_code": 200, "body": result},
                    ),
                )
                return
            if message.op == "usage.record":
                body = message.payload.get("body", {})
                if not isinstance(body, dict):
                    raise ValueError("invalid usage.record payload")
                result = await self.dispatcher.record_usage_event(body)
                await self._send(
                    websocket,
                    ResponseEndMessage(
                        type="response_end",
                        request_id=message.request_id,
                        device_id=self.device_id,
                        op=message.op,
                        payload={"status_code": 202, "body": result},
                    ),
                )
                return
            if message.op == "account.sync_upsert":
                body = message.payload.get("body", {})
                if not isinstance(body, dict):
                    raise ValueError("invalid account.sync_upsert payload")
                result = await self.dispatcher.sync_account_upsert(body)
                await self._send(
                    websocket,
                    ResponseEndMessage(
                        type="response_end",
                        request_id=message.request_id,
                        device_id=self.device_id,
                        op=message.op,
                        payload={"status_code": 200, "body": result},
                    ),
                )
                return
            if message.op == "account.sync_status":
                body = message.payload.get("body", {})
                if not isinstance(body, dict):
                    raise ValueError("invalid account.sync_status payload")
                public_account_id = body.get("account_id")
                if not isinstance(public_account_id, str) or not public_account_id:
                    raise ValueError("invalid account.sync_status account_id")
                result = await self.dispatcher.get_account_mirror_status(public_account_id)
                await self._send(
                    websocket,
                    ResponseEndMessage(
                        type="response_end",
                        request_id=message.request_id,
                        device_id=self.device_id,
                        op=message.op,
                        payload={"status_code": 200, "body": result},
                    ),
                )
                return
            if message.op == "api_key.sync_upsert":
                body = message.payload.get("body", {})
                if not isinstance(body, dict):
                    raise ValueError("invalid api_key.sync_upsert payload")
                result = await self.dispatcher.sync_api_key_upsert(body)
                await self._send(
                    websocket,
                    ResponseEndMessage(
                        type="response_end",
                        request_id=message.request_id,
                        device_id=self.device_id,
                        op=message.op,
                        payload={"status_code": 200, "body": result},
                    ),
                )
                return
            if message.op == "api_key.sync_revoke":
                body = message.payload.get("body", {})
                if not isinstance(body, dict):
                    raise ValueError("invalid api_key.sync_revoke payload")
                result = await self.dispatcher.sync_api_key_revoke(body)
                await self._send(
                    websocket,
                    ResponseEndMessage(
                        type="response_end",
                        request_id=message.request_id,
                        device_id=self.device_id,
                        op=message.op,
                        payload={"status_code": 200, "body": result},
                    ),
                )
                return
            if message.op == "chat.complete":
                headers = message.payload.get("headers", {})
                body = message.payload.get("body", {})
                if not isinstance(headers, dict) or not isinstance(body, dict):
                    raise ValueError("invalid chat.complete payload")
                authorization = str(headers["authorization"])
                request_payload = dict(body)
                if request_payload.get("stream"):
                    async for chunk in self.dispatcher.chat_complete_stream(
                        authorization=authorization,
                        payload=request_payload,
                    ):
                        await self._send(
                            websocket,
                            ResponseChunkMessage(
                                type="response_chunk",
                                request_id=message.request_id,
                                device_id=self.device_id,
                                op=message.op,
                                payload={"chunk": chunk},
                            ),
                        )
                    await self._send(
                        websocket,
                        ResponseEndMessage(
                            type="response_end",
                            request_id=message.request_id,
                            device_id=self.device_id,
                            op=message.op,
                            payload={"status_code": 200},
                        ),
                    )
                    return

                result = await self.dispatcher.chat_complete(
                    authorization=authorization,
                    payload=request_payload,
                )
                await self._send(
                    websocket,
                    ResponseEndMessage(
                        type="response_end",
                        request_id=message.request_id,
                        device_id=self.device_id,
                        op=message.op,
                        payload={"status_code": 200, "body": result},
                    ),
                )
                return

            raise ValueError(f"unsupported op: {message.op}")
        except asyncio.CancelledError:
            await self._send(
                websocket,
                ResponseErrorMessage(
                    type="response_error",
                    request_id=message.request_id,
                    device_id=self.device_id,
                    op=message.op,
                    payload={"status_code": 499, "code": "cancelled", "detail": "request cancelled"},
                ),
            )
            raise
        except Exception as exc:  # noqa: BLE001
            await self._send(
                websocket,
                ResponseErrorMessage(
                    type="response_error",
                    request_id=message.request_id,
                    device_id=self.device_id,
                    op=message.op,
                    payload={"status_code": 502, "code": "request_failed", "detail": str(exc)},
                ),
            )
        finally:
            self._inflight.pop(message.request_id, None)

    async def _send(self, websocket: Any, message: Any) -> None:
        async with self._send_lock:
            await websocket.send(serialize_tunnel_message(message))
