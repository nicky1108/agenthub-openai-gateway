from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from app.core.settings import Settings

_SECRET_PREFIX = "enc:v1:"
_NONCE_BYTES = 16


def is_sealed_secret(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith(_SECRET_PREFIX)


def seal_secret(value: str | None) -> str | None:
    if value is None:
        return None
    if is_sealed_secret(value):
        return value
    raw = value.encode("utf-8")
    key = _secret_key()
    nonce = secrets.token_bytes(_NONCE_BYTES)
    ciphertext = _xor_bytes(raw, _keystream(key, nonce, len(raw)))
    tag = hmac.new(key, b"enc:v1:" + nonce + ciphertext, hashlib.sha256).digest()
    return _SECRET_PREFIX + ":".join(
        [_b64_encode(nonce), _b64_encode(ciphertext), _b64_encode(tag)]
    )


def reveal_secret(value: str | None) -> str | None:
    if value is None or not is_sealed_secret(value):
        return value
    try:
        nonce_text, ciphertext_text, tag_text = value[len(_SECRET_PREFIX) :].split(":", 2)
        nonce = _b64_decode(nonce_text)
        ciphertext = _b64_decode(ciphertext_text)
        tag = _b64_decode(tag_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid encrypted secret") from exc
    key = _secret_key()
    expected_tag = hmac.new(key, b"enc:v1:" + nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("invalid encrypted secret")
    plaintext = _xor_bytes(ciphertext, _keystream(key, nonce, len(ciphertext)))
    return plaintext.decode("utf-8")


def _secret_key() -> bytes:
    settings = Settings()
    key_material = settings.secret_encryption_key or settings.admin_secret
    return hashlib.sha256(key_material.encode("utf-8")).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < length:
        output.extend(
            hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        )
        counter += 1
    return bytes(output[:length])


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(left_byte ^ right_byte for left_byte, right_byte in zip(left, right, strict=True))


def _b64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
