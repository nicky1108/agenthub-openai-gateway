from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class ProviderRuntimeHandle:
    key: str
    payload: dict[str, Any]


class ProviderProcessPool:
    def __init__(self) -> None:
        self._handles: dict[str, ProviderRuntimeHandle] = {}

    def get_or_create(
        self,
        *,
        key: str,
        factory: Callable[[], dict[str, Any]],
    ) -> ProviderRuntimeHandle:
        handle = self._handles.get(key)
        if handle is not None:
            return handle
        handle = ProviderRuntimeHandle(key=key, payload=factory())
        self._handles[key] = handle
        return handle

    def invalidate(self, key: str) -> None:
        self._handles.pop(key, None)

    def clear(self) -> None:
        self._handles.clear()

    def size(self) -> int:
        return len(self._handles)


provider_process_pool = ProviderProcessPool()
