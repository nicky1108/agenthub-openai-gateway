from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter


TunnelOperation = Literal[
    "key.introspect",
    "catalog.platform_models",
    "chat.complete",
    "usage.record",
]


class HelloPayload(BaseModel):
    timestamp: int
    nonce: str
    signature: str


class HelloMessage(BaseModel):
    type: Literal["hello"]
    device_id: str
    payload: HelloPayload


class HelloAckMessage(BaseModel):
    type: Literal["hello_ack"]
    device_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class PingMessage(BaseModel):
    type: Literal["ping"]
    device_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class PongMessage(BaseModel):
    type: Literal["pong"]
    device_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class RequestMessage(BaseModel):
    type: Literal["request"]
    request_id: str
    device_id: str
    op: TunnelOperation
    payload: dict[str, Any]


class ResponseStartMessage(BaseModel):
    type: Literal["response_start"]
    request_id: str
    device_id: str
    op: TunnelOperation
    payload: dict[str, Any] = Field(default_factory=dict)


class ResponseChunkMessage(BaseModel):
    type: Literal["response_chunk"]
    request_id: str
    device_id: str
    op: TunnelOperation
    payload: dict[str, Any]


class ResponseEndMessage(BaseModel):
    type: Literal["response_end"]
    request_id: str
    device_id: str
    op: TunnelOperation
    payload: dict[str, Any] = Field(default_factory=dict)


class ResponseErrorMessage(BaseModel):
    type: Literal["response_error"]
    request_id: str
    device_id: str
    op: TunnelOperation
    payload: dict[str, Any]


class CancelMessage(BaseModel):
    type: Literal["cancel"]
    request_id: str
    device_id: str
    op: TunnelOperation | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


TunnelMessage = Union[
    HelloMessage,
    HelloAckMessage,
    PingMessage,
    PongMessage,
    RequestMessage,
    ResponseStartMessage,
    ResponseChunkMessage,
    ResponseEndMessage,
    ResponseErrorMessage,
    CancelMessage,
]


_TUNNEL_MESSAGE_ADAPTER = TypeAdapter(TunnelMessage)


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def build_hello_signature(
    *,
    device_id: str,
    timestamp: int,
    nonce: str,
    secret: str,
) -> str:
    message = canonical_json(
        {
            "device_id": device_id,
            "timestamp": timestamp,
            "nonce": nonce,
        }
    )
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def build_hello_message(
    *,
    device_id: str,
    secret: str,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> HelloMessage:
    resolved_timestamp = int(timestamp if timestamp is not None else time.time())
    resolved_nonce = nonce or secrets.token_hex(16)
    return HelloMessage(
        type="hello",
        device_id=device_id,
        payload=HelloPayload(
            timestamp=resolved_timestamp,
            nonce=resolved_nonce,
            signature=build_hello_signature(
                device_id=device_id,
                timestamp=resolved_timestamp,
                nonce=resolved_nonce,
                secret=secret,
            ),
        ),
    )


def verify_hello_message(
    message: HelloMessage,
    *,
    secret: str,
    now: int | None = None,
    max_skew_seconds: int = 60,
) -> bool:
    resolved_now = int(now if now is not None else time.time())
    expected = build_hello_signature(
        device_id=message.device_id,
        timestamp=message.payload.timestamp,
        nonce=message.payload.nonce,
        secret=secret,
    )
    if not hmac.compare_digest(message.payload.signature, expected):
        return False
    if abs(resolved_now - message.payload.timestamp) > max_skew_seconds:
        return False
    return True


def parse_tunnel_message(raw: str | bytes) -> TunnelMessage:
    if isinstance(raw, bytes):
        raw = raw.decode()
    return _TUNNEL_MESSAGE_ADAPTER.validate_json(raw)


def serialize_tunnel_message(message: TunnelMessage) -> str:
    return message.model_dump_json(exclude_none=True)
