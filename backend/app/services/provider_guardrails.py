from __future__ import annotations

from ipaddress import ip_address
from socket import getaddrinfo, inet_aton
from collections.abc import Callable, Sequence
from urllib.parse import urlparse

Resolver = Callable[[str], Sequence[str]]


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


def ensure_safe_provider_url(
    value: str,
    *,
    resolver: Resolver | None = None,
    strict_dns: bool = False,
) -> str:
    parsed = urlparse(value)
    hostname = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ValueError("unsafe provider url")
    if parsed.username or parsed.password:
        raise ValueError("unsafe provider url")
    normalized_host = hostname.strip().rstrip(".").lower()
    if normalized_host == "localhost" or normalized_host.endswith(".localhost"):
        raise ValueError("unsafe provider url")
    ip = _parse_ip_host(normalized_host)
    if ip is not None and not ip.is_global:
        raise ValueError("unsafe provider url")
    if ip is None:
        _ensure_public_dns_resolution(normalized_host, resolver=resolver, strict_dns=strict_dns)
    return value.rstrip("/")


def _parse_ip_host(hostname: str):
    try:
        return ip_address(hostname)
    except ValueError:
        try:
            return ip_address(inet_aton(hostname))
        except OSError:
            return None


def _ensure_public_dns_resolution(hostname: str, *, resolver: Resolver | None, strict_dns: bool) -> None:
    resolve = resolver or _default_resolver
    try:
        addresses = list(resolve(hostname))
    except OSError as exc:
        if strict_dns:
            raise ValueError("unsafe provider url") from exc
        return
    if not addresses:
        if strict_dns:
            raise ValueError("unsafe provider url")
        return
    for address in addresses:
        ip = _parse_ip_host(address)
        if ip is None or not ip.is_global:
            raise ValueError("unsafe provider url")


def _default_resolver(hostname: str) -> list[str]:
    return sorted(
        {
            str(item[4][0])
            for item in getaddrinfo(hostname, None)
            if item and len(item) >= 5
        }
    )
