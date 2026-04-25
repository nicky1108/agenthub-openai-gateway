from __future__ import annotations

from ipaddress import ip_address
from socket import inet_aton
from urllib.parse import urlparse


def ensure_safe_provider_slug(slug: str, reserved: set[str]) -> str:
    normalized = slug.strip().lower()
    if not normalized or ":" in normalized:
        raise ValueError("invalid provider slug")
    if normalized in {item.strip().lower() for item in reserved}:
        raise ValueError("reserved provider slug")
    return normalized


def ensure_safe_provider_protocol(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"openai", "anthropic"}:
        raise ValueError("unsupported provider protocol")
    return normalized


def ensure_safe_provider_url(value: str) -> str:
    parsed = urlparse(value)
    hostname = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ValueError("unsafe provider url")
    if hostname == "localhost":
        raise ValueError("unsafe provider url")
    ip = _parse_ip_host(hostname)
    if ip is not None and not ip.is_global:
        raise ValueError("unsafe provider url")
    return value.rstrip("/")


def _parse_ip_host(hostname: str):
    try:
        return ip_address(hostname)
    except ValueError:
        try:
            return ip_address(inet_aton(hostname))
        except OSError:
            return None

